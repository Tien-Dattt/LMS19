# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsQuestionBankExam(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Program = cls.env["elearning.program"]
        cls.ProgramPartner = cls.env["elearning.program.partner"]
        cls.TrainingClass = cls.env["elearning.class"]
        cls.ClassStudent = cls.env["elearning.class.student"]
        cls.QuestionBank = cls.env["elearning.question.bank"]
        cls.Question = cls.env["elearning.question"]
        cls.Exam = cls.env["elearning.exam"]
        cls.Session = cls.env["elearning.exam.session"]
        cls.Gradebook = cls.env["elearning.gradebook"]
        cls.GradebookLine = cls.env["elearning.gradebook.line"]

        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_exam_training_manager",
            name="Corporate LMS Exam Training Manager",
            email="corporate.lms.exam.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.instructor = mail_new_test_user(
            cls.env,
            login="corporate_lms_exam_instructor",
            name="Corporate LMS Exam Instructor",
            email="corporate.lms.exam.instructor@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_instructor",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_exam_learner",
            name="Corporate LMS Exam Learner",
            email="corporate.lms.exam.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_exam_other_learner",
            name="Corporate LMS Exam Other Learner",
            email="corporate.lms.exam.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.program = cls.Program.create({
            "name": "Exam Program",
            "code": "EXAM-PROGRAM",
            "state": "published",
            "passing_score": 70.0,
        })
        cls.ProgramPartner.create({
            "program_id": cls.program.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "in_progress",
        })
        cls.training_class = cls.TrainingClass.create({
            "name": "Exam Class",
            "code": "EXAM-CLASS",
            "program_id": cls.program.id,
            "trainer_ids": [(6, 0, [cls.instructor.id])],
        })
        cls.ClassStudent.create({
            "class_id": cls.training_class.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "active",
        })

        cls.bank = cls.QuestionBank.with_user(cls.training_manager).create({
            "name": "Leadership Exam Bank",
            "program_id": cls.program.id,
            "owner_id": cls.training_manager.id,
            "state": "active",
        })
        cls.single_question = cls.Question.with_user(cls.training_manager).create({
            "bank_id": cls.bank.id,
            "name": "Which behavior is expected from a team lead?",
            "question_type": "single",
            "difficulty": "medium",
            "score": 40.0,
            "state": "active",
            "answer_ids": [
                (0, 0, {"name": "Coach the team", "is_correct": True, "sequence": 10}),
                (0, 0, {"name": "Avoid feedback", "sequence": 20}),
            ],
        })
        cls.single_correct_answer = cls.single_question.answer_ids.filtered("is_correct")
        cls.single_wrong_answer = cls.single_question.answer_ids - cls.single_correct_answer
        cls.multiple_question = cls.Question.with_user(cls.training_manager).create({
            "bank_id": cls.bank.id,
            "name": "Which items support a training plan?",
            "question_type": "multiple",
            "difficulty": "medium",
            "score": 60.0,
            "ai_explanation": "<p>Draft rationale only.</p>",
            "state": "active",
            "answer_ids": [
                (0, 0, {"name": "Role track", "is_correct": True, "sequence": 10}),
                (0, 0, {"name": "Employee level", "is_correct": True, "sequence": 20}),
                (0, 0, {"name": "Unreviewed AI score", "sequence": 30}),
            ],
        })
        cls.multiple_correct_answers = cls.multiple_question.answer_ids.filtered("is_correct")

    def _create_exam(self, **values):
        defaults = {
            "name": "Leadership Readiness Exam",
            "program_id": self.program.id,
            "class_id": self.training_class.id,
            "question_bank_id": self.bank.id,
            "question_count": 2,
            "attempt_limit": 1,
            "passing_score": 70.0,
            "state": "published",
        }
        defaults.update(values)
        return self.Exam.with_user(self.training_manager).create(defaults)

    def test_active_choice_question_requires_correct_answer(self):
        question = self.Question.with_user(self.training_manager).create({
            "bank_id": self.bank.id,
            "name": "Draft question without a correct answer",
            "question_type": "single",
            "difficulty": "easy",
            "score": 10.0,
            "state": "draft",
            "answer_ids": [(0, 0, {"name": "Incorrect option"})],
        })

        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            question.action_activate()

        question.answer_ids.with_user(self.training_manager).write({"is_correct": True})
        question.action_activate()
        self.assertEqual(question.state, "active")

    def test_ai_explanation_question_stays_draft_until_reviewed(self):
        question = self.Question.with_user(self.training_manager).create({
            "bank_id": self.bank.id,
            "name": "AI generated draft question",
            "question_type": "single",
            "difficulty": "medium",
            "score": 10.0,
            "ai_explanation": "<p>Draft helper content.</p>",
            "answer_ids": [(0, 0, {"name": "Draft answer", "is_correct": True})],
        })

        self.assertEqual(question.state, "draft")
        self.assertTrue(question.ai_explanation)

    def test_cannot_publish_exam_without_enough_active_questions(self):
        exam = self.Exam.with_user(self.training_manager).create({
            "name": "Too Many Questions Exam",
            "program_id": self.program.id,
            "class_id": self.training_class.id,
            "question_bank_id": self.bank.id,
            "question_count": 99,
            "state": "draft",
        })

        with self.assertRaises(ValidationError):
            exam.action_publish()

    def test_learner_only_sees_assigned_published_exams(self):
        visible_exam = self._create_exam(name="Visible Published Exam")
        draft_exam = self._create_exam(name="Draft Exam", state="draft")
        unassigned_program = self.Program.create({
            "name": "Unassigned Exam Program",
            "code": "UNASSIGNED-EXAM",
            "state": "published",
        })
        hidden_exam = self._create_exam(
            name="Hidden Exam",
            program_id=unassigned_program.id,
            class_id=False,
        )

        visible = self.Exam.with_user(self.learner).search([
            ("id", "in", (visible_exam | draft_exam | hidden_exam).ids),
        ])

        self.assertEqual(visible, visible_exam)

    def test_learner_cannot_exceed_attempt_limit(self):
        exam = self._create_exam()

        session = exam.with_user(self.learner).action_start_exam()

        self.assertEqual(session.state, "in_progress")
        self.assertEqual(len(session.line_ids), 2)
        with self.assertRaises(ValidationError):
            exam.with_user(self.learner).action_start_exam()

    def test_submit_scores_exam_and_updates_gradebook(self):
        exam = self._create_exam()
        session = exam.with_user(self.learner).action_start_exam()
        single_line = session.line_ids.filtered(lambda line: line.question_id == self.single_question)
        multiple_line = session.line_ids.filtered(lambda line: line.question_id == self.multiple_question)

        single_line.with_user(self.learner).write({
            "selected_answer_ids": [(6, 0, self.single_correct_answer.ids)],
        })
        multiple_line.with_user(self.learner).write({
            "selected_answer_ids": [(6, 0, self.multiple_correct_answers.ids)],
        })
        session.with_user(self.learner).action_submit()

        self.assertEqual(session.state, "graded")
        self.assertEqual(session.score, 100.0)
        self.assertTrue(session.passed)
        self.assertTrue(all(session.line_ids.mapped("is_correct")))

        gradebook = self.Gradebook.search([
            ("program_id", "=", self.program.id),
            ("class_id", "=", self.training_class.id),
            ("partner_id", "=", self.learner.partner_id.id),
        ])
        self.assertEqual(len(gradebook), 1)
        line = self.GradebookLine.search([
            ("gradebook_id", "=", gradebook.id),
            ("source_type", "=", "exam"),
            ("exam_session_id", "=", session.id),
        ])
        self.assertEqual(len(line), 1)
        self.assertEqual(line.score, 100.0)
        self.assertEqual(gradebook.final_score, 100.0)

    def test_learner_cannot_write_official_exam_score(self):
        exam = self._create_exam()
        session = exam.with_user(self.learner).action_start_exam()

        with self.assertRaises(AccessError):
            session.with_user(self.learner).write({"score": 100.0})

    def test_learner_only_reads_own_exam_sessions(self):
        exam = self._create_exam(attempt_limit=0)
        own_session = exam.with_user(self.learner).action_start_exam()
        other_session = self.Session.with_user(self.training_manager).create({
            "exam_id": exam.id,
            "partner_id": self.other_learner.partner_id.id,
        })

        visible = self.Session.with_user(self.learner).search([
            ("id", "in", (own_session | other_session).ids),
        ])

        self.assertEqual(visible, own_session)
