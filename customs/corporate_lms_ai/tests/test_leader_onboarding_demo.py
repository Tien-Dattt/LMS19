# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged
from odoo.tools.convert import convert_file


@tagged("-at_install", "post_install")
class TestCorporateLmsLeaderOnboardingDemo(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        idref = {}
        for module, filename in (
            ("corporate_lms_base", "demo/leader_onboarding_demo.xml"),
            ("corporate_lms_assessment", "demo/leader_onboarding_assessment_demo.xml"),
            ("corporate_lms_ai", "demo/leader_onboarding_ai_demo.xml"),
        ):
            convert_file(cls.env, module, filename, idref, mode="init", noupdate=False)

    def test_leader_onboarding_demo_records_and_flow(self):
        learner = self.env.ref("corporate_lms_base.user_leader_onboarding_learner")
        instructor = self.env.ref("corporate_lms_base.user_leader_onboarding_instructor")
        program = self.env.ref("corporate_lms_base.program_leader_onboarding")
        course = self.env.ref("corporate_lms_base.slide_channel_leader_onboarding")
        learner_partner = self.env.ref("corporate_lms_base.partner_leader_onboarding_learner")
        employee = self.env.ref("corporate_lms_base.employee_leader_onboarding_learner")
        matrix = self.env.ref("corporate_lms_base.matrix_leader_onboarding_it_team_leader")
        training_class = self.env.ref("corporate_lms_base.class_leader_batch_01")
        assignment = self.env.ref("corporate_lms_assessment.assignment_leadership_case_study")
        submission = self.env.ref("corporate_lms_assessment.submission_leadership_case_study")
        exam = self.env.ref("corporate_lms_assessment.exam_leader_onboarding")
        ai_source = self.env.ref("corporate_lms_ai.ai_source_leader_onboarding_course")

        self.assertEqual(matrix.program_id, program)
        self.assertEqual(employee.department_id.name, "IT")
        self.assertEqual(employee.job_id.name, "Team Leader")
        self.assertEqual(employee.employee_level_id.name, "Leader")
        self.assertEqual(employee.role_track_id.name, "People Leader")
        self.assertEqual(training_class.name, "Leader Batch 01")
        self.assertEqual(assignment.rubric_id.name, "Leadership Rubric")
        self.assertEqual(exam.question_bank_id.name, "Leader Onboarding Question Bank")
        self.assertEqual(ai_source.type, "elearning_course")
        self.assertEqual(ai_source.channel_id, course)

        enrollment = self.env["elearning.program.partner"].search([
            ("program_id", "=", program.id),
            ("partner_id", "=", learner_partner.id),
        ], limit=1)
        self.assertTrue(enrollment)
        self.assertEqual(enrollment.source, "matrix")
        self.assertEqual(enrollment.state, "in_progress")

        membership = self.env["slide.channel.partner"].sudo().search([
            ("channel_id", "=", course.id),
            ("partner_id", "=", learner_partner.id),
            ("member_status", "!=", "invited"),
        ], limit=1)
        self.assertTrue(membership)

        course.slide_ids.with_user(learner).action_mark_completed()
        enrollment.invalidate_recordset(["progress"])
        self.assertEqual(enrollment.progress, 100.0)

        self.assertTrue(submission.ai_feedback_draft)
        self.assertFalse(submission.feedback)
        submission.with_user(instructor).write({
            "score": 45.0,
            "feedback": "<p>Official instructor feedback for the demo case study.</p>",
        })
        submission.with_user(instructor).action_grade()
        self.assertEqual(submission.state, "graded")
        self.assertNotEqual(submission.feedback, submission.ai_feedback_draft)

        session = exam.with_user(learner).action_start_exam()
        for line in session.line_ids:
            correct_answer_ids = line.sudo().question_id.answer_ids.filtered("is_correct").ids
            line.with_user(learner).write({
                "selected_answer_ids": [(6, 0, correct_answer_ids)],
            })
        session.with_user(learner).action_submit()
        self.assertEqual(session.state, "graded")
        self.assertTrue(session.passed)

        gradebook = self.env["elearning.gradebook"].search([
            ("program_id", "=", program.id),
            ("class_id", "=", training_class.id),
            ("partner_id", "=", learner_partner.id),
        ], limit=1)
        self.assertTrue(gradebook)
        self.assertEqual(gradebook.final_score, 100.0)
        gradebook.action_finalize()
        self.assertTrue(gradebook.passed)
        self.assertEqual(enrollment.state, "completed")
        self.assertEqual(enrollment.final_score, 100.0)
        self.assertTrue(ai_source.with_user(learner).user_has_access)
