# -*- coding: utf-8 -*-

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsAssessmentReports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.training_manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_assessment_report_training_manager",
            name="Corporate LMS Assessment Report Training Manager",
            email="corporate.lms.assessment.report.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_training_manager",
        )
        cls.manager = mail_new_test_user(
            cls.env,
            login="corporate_lms_assessment_report_manager",
            name="Corporate LMS Assessment Report Manager",
            email="corporate.lms.assessment.report.team.manager@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_manager",
        )
        cls.learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_assessment_report_learner",
            name="Corporate LMS Assessment Report Learner",
            email="corporate.lms.assessment.report.learner@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.other_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_assessment_report_other",
            name="Corporate LMS Assessment Report Other Learner",
            email="corporate.lms.assessment.report.other@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )
        cls.hidden_learner = mail_new_test_user(
            cls.env,
            login="corporate_lms_assessment_report_hidden",
            name="Corporate LMS Assessment Report Hidden Learner",
            email="corporate.lms.assessment.report.hidden@example.com",
            groups="base.group_user,corporate_lms_base.group_corporate_lms_learner",
        )

        cls.program = cls.env["elearning.program"].create({
            "name": "Assessment Report Program",
            "code": "ASSESSMENT-REPORT-PROGRAM",
            "state": "published",
            "passing_score": 70.0,
        })
        cls.report_class = cls.env["elearning.class"].create({
            "name": "Assessment Report Class",
            "code": "ASSESSMENT-REPORT-CLASS",
            "program_id": cls.program.id,
            "trainer_ids": [(6, 0, [cls.manager.id])],
            "state": "running",
        })
        cls.hidden_class = cls.env["elearning.class"].create({
            "name": "Assessment Hidden Report Class",
            "code": "ASSESSMENT-HIDDEN-REPORT-CLASS",
            "program_id": cls.program.id,
            "state": "running",
        })
        cls.env["elearning.class.student"].create({
            "class_id": cls.report_class.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "active",
        })
        cls.env["elearning.class.student"].create({
            "class_id": cls.report_class.id,
            "partner_id": cls.other_learner.partner_id.id,
            "state": "active",
        })
        cls.env["elearning.class.student"].create({
            "class_id": cls.hidden_class.id,
            "partner_id": cls.hidden_learner.partner_id.id,
            "state": "active",
        })

        cls.assignment = cls.env["elearning.assignment"].with_user(cls.training_manager).create({
            "name": "Assessment Report Assignment",
            "description": "<p>Report assignment.</p>",
            "program_id": cls.program.id,
            "class_id": cls.report_class.id,
            "state": "published",
        })
        cls.hidden_assignment = cls.env["elearning.assignment"].with_user(cls.training_manager).create({
            "name": "Assessment Hidden Assignment",
            "description": "<p>Hidden assignment.</p>",
            "program_id": cls.program.id,
            "class_id": cls.hidden_class.id,
            "state": "published",
        })
        cls.own_submission = cls.env["elearning.assignment.submission"].with_user(cls.training_manager).create({
            "assignment_id": cls.assignment.id,
            "partner_id": cls.learner.partner_id.id,
            "text_answer": "<p>Own answer.</p>",
            "score": 80.0,
        })
        cls.other_submission = cls.env["elearning.assignment.submission"].with_user(cls.training_manager).create({
            "assignment_id": cls.assignment.id,
            "partner_id": cls.other_learner.partner_id.id,
            "text_answer": "<p>Other answer.</p>",
            "score": 55.0,
        })
        cls.hidden_submission = cls.env["elearning.assignment.submission"].with_user(cls.training_manager).create({
            "assignment_id": cls.hidden_assignment.id,
            "partner_id": cls.hidden_learner.partner_id.id,
            "text_answer": "<p>Hidden answer.</p>",
            "score": 20.0,
        })

        cls.question_bank = cls.env["elearning.question.bank"].with_user(cls.training_manager).create({
            "name": "Assessment Report Bank",
            "program_id": cls.program.id,
            "owner_id": cls.training_manager.id,
            "state": "active",
        })
        cls.env["elearning.question"].with_user(cls.training_manager).create({
            "bank_id": cls.question_bank.id,
            "name": "Assessment report question?",
            "question_type": "single",
            "score": 10.0,
            "state": "active",
            "answer_ids": [
                (0, 0, {"name": "Correct", "is_correct": True}),
                (0, 0, {"name": "Wrong"}),
            ],
        })
        cls.exam = cls.env["elearning.exam"].with_user(cls.training_manager).create({
            "name": "Assessment Report Exam",
            "program_id": cls.program.id,
            "class_id": cls.report_class.id,
            "question_bank_id": cls.question_bank.id,
            "question_count": 1,
            "attempt_limit": 0,
            "state": "published",
        })
        cls.hidden_exam = cls.env["elearning.exam"].with_user(cls.training_manager).create({
            "name": "Assessment Hidden Report Exam",
            "program_id": cls.program.id,
            "class_id": cls.hidden_class.id,
            "question_bank_id": cls.question_bank.id,
            "question_count": 1,
            "attempt_limit": 0,
            "state": "published",
        })
        cls.own_session = cls.env["elearning.exam.session"].with_user(cls.training_manager).create({
            "exam_id": cls.exam.id,
            "partner_id": cls.learner.partner_id.id,
        })
        cls.other_session = cls.env["elearning.exam.session"].with_user(cls.training_manager).create({
            "exam_id": cls.exam.id,
            "partner_id": cls.other_learner.partner_id.id,
        })
        cls.hidden_session = cls.env["elearning.exam.session"].with_user(cls.training_manager).create({
            "exam_id": cls.hidden_exam.id,
            "partner_id": cls.hidden_learner.partner_id.id,
        })

        cls.own_gradebook = cls.env["elearning.gradebook"].with_user(cls.training_manager).create({
            "program_id": cls.program.id,
            "class_id": cls.report_class.id,
            "partner_id": cls.learner.partner_id.id,
            "state": "open",
            "line_ids": [(0, 0, {"source_type": "manual", "score": 80.0})],
        })
        cls.other_gradebook = cls.env["elearning.gradebook"].with_user(cls.training_manager).create({
            "program_id": cls.program.id,
            "class_id": cls.report_class.id,
            "partner_id": cls.other_learner.partner_id.id,
            "state": "open",
            "line_ids": [(0, 0, {"source_type": "manual", "score": 55.0})],
        })
        cls.hidden_gradebook = cls.env["elearning.gradebook"].with_user(cls.training_manager).create({
            "program_id": cls.program.id,
            "class_id": cls.hidden_class.id,
            "partner_id": cls.hidden_learner.partner_id.id,
            "state": "open",
            "line_ids": [(0, 0, {"source_type": "manual", "score": 20.0})],
        })

    def test_report_actions_and_fields_exist(self):
        for xmlid, model_name in (
            ("corporate_lms_assessment.action_report_assignment_submission", "elearning.assignment.submission"),
            ("corporate_lms_assessment.action_report_exam_session", "elearning.exam.session"),
            ("corporate_lms_assessment.action_report_gradebook", "elearning.gradebook"),
        ):
            action = self.env.ref(xmlid)
            self.assertEqual(action.res_model, model_name)
            self.assertIn("pivot", action.view_mode)

        for field_name in ("assignment_program_id", "assignment_channel_id", "assignment_class_id", "grader_id"):
            self.assertIn(field_name, self.env["elearning.assignment.submission"]._fields)
        for field_name in ("exam_program_id", "exam_channel_id", "exam_class_id"):
            self.assertIn(field_name, self.env["elearning.exam.session"]._fields)

    def test_assignment_grader_is_recorded_for_report(self):
        self.own_submission.with_user(self.training_manager).action_grade()
        self.assertEqual(self.own_submission.grader_id, self.training_manager)

    def test_training_manager_sees_all_assessment_report_records(self):
        submissions = self.env["elearning.assignment.submission"].with_user(self.training_manager).search([
            ("id", "in", (self.own_submission | self.other_submission | self.hidden_submission).ids),
        ])
        sessions = self.env["elearning.exam.session"].with_user(self.training_manager).search([
            ("id", "in", (self.own_session | self.other_session | self.hidden_session).ids),
        ])
        gradebooks = self.env["elearning.gradebook"].with_user(self.training_manager).search([
            ("id", "in", (self.own_gradebook | self.other_gradebook | self.hidden_gradebook).ids),
        ])

        self.assertEqual(set(submissions.ids), set((self.own_submission | self.other_submission | self.hidden_submission).ids))
        self.assertEqual(set(sessions.ids), set((self.own_session | self.other_session | self.hidden_session).ids))
        self.assertEqual(set(gradebooks.ids), set((self.own_gradebook | self.other_gradebook | self.hidden_gradebook).ids))

    def test_learner_sees_only_own_assessment_report_records(self):
        submissions = self.env["elearning.assignment.submission"].with_user(self.learner).search([
            ("id", "in", (self.own_submission | self.other_submission | self.hidden_submission).ids),
        ])
        sessions = self.env["elearning.exam.session"].with_user(self.learner).search([
            ("id", "in", (self.own_session | self.other_session | self.hidden_session).ids),
        ])
        gradebooks = self.env["elearning.gradebook"].with_user(self.learner).search([
            ("id", "in", (self.own_gradebook | self.other_gradebook | self.hidden_gradebook).ids),
        ])

        self.assertEqual(submissions, self.own_submission)
        self.assertEqual(sessions, self.own_session)
        self.assertEqual(gradebooks, self.own_gradebook)

    def test_manager_sees_assigned_class_report_records_only(self):
        submissions = self.env["elearning.assignment.submission"].with_user(self.manager).search([
            ("id", "in", (self.own_submission | self.other_submission | self.hidden_submission).ids),
        ])
        sessions = self.env["elearning.exam.session"].with_user(self.manager).search([
            ("id", "in", (self.own_session | self.other_session | self.hidden_session).ids),
        ])
        gradebooks = self.env["elearning.gradebook"].with_user(self.manager).search([
            ("id", "in", (self.own_gradebook | self.other_gradebook | self.hidden_gradebook).ids),
        ])

        self.assertEqual(set(submissions.ids), set((self.own_submission | self.other_submission).ids))
        self.assertEqual(set(sessions.ids), set((self.own_session | self.other_session).ids))
        self.assertEqual(set(gradebooks.ids), set((self.own_gradebook | self.other_gradebook).ids))
