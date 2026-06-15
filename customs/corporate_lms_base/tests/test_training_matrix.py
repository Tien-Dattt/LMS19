# -*- coding: utf-8 -*-

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("-at_install", "post_install")
class TestCorporateLmsTrainingMatrix(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Level = cls.env["elearning.employee.level"]
        cls.RoleTrack = cls.env["elearning.role.track"]
        cls.Program = cls.env["elearning.program"]
        cls.Matrix = cls.env["elearning.training.matrix"]

    def test_level_active_code_unique_and_inactive_duplicate_allowed(self):
        self.Level.create({"name": "Leader", "code": "LEADER"})

        with self.assertRaises(ValidationError):
            self.Level.create({"name": "Leader Duplicate", "code": "LEADER"})

        inactive = self.Level.create({
            "name": "Archived Leader",
            "code": "LEADER",
            "active": False,
        })
        with self.assertRaises(ValidationError):
            inactive.active = True

    def test_role_track_active_code_unique_and_inactive_duplicate_allowed(self):
        self.RoleTrack.create({"name": "People Leader", "code": "PEOPLE"})

        with self.assertRaises(ValidationError):
            self.RoleTrack.create({"name": "People Leader Duplicate", "code": "PEOPLE"})

        inactive = self.RoleTrack.create({
            "name": "Archived People Leader",
            "code": "PEOPLE",
            "active": False,
        })
        with self.assertRaises(ValidationError):
            inactive.active = True

    def test_used_level_is_archived_instead_of_deleted(self):
        level = self.Level.create({"name": "Senior", "code": "SENIOR"})
        program = self.Program.create({
            "name": "Leadership Basics",
            "code": "LEAD-BASIC",
            "state": "published",
        })
        self.Matrix.create({
            "name": "Senior Matrix",
            "employee_level_id": level.id,
            "program_id": program.id,
        })

        level.unlink()
        self.assertTrue(level.exists())
        self.assertFalse(level.active)

    def test_matrix_matching_priority(self):
        department = self.env["hr.department"].create({"name": "Engineering"})
        job = self.env["hr.job"].create({"name": "Team Lead"})
        level = self.Level.create({"name": "Leader", "code": "LEAD"})
        role = self.RoleTrack.create({"name": "People Leader", "code": "PEOPLE"})
        employee = self.env["hr.employee"].create({
            "name": "Leader Employee",
            "department_id": department.id,
            "job_id": job.id,
            "employee_level_id": level.id,
            "role_track_id": role.id,
        })
        programs = self.Program.create([
            {"name": "Level Program", "code": "P-LEVEL", "state": "published"},
            {"name": "Department Level Program", "code": "P-DEPT-LEVEL", "state": "published"},
            {"name": "Job Level Program", "code": "P-JOB-LEVEL", "state": "published"},
            {"name": "Job Level Role Program", "code": "P-JOB-LEVEL-ROLE", "state": "published"},
        ])
        matrices = self.Matrix.create([
            {
                "name": "Level",
                "employee_level_id": level.id,
                "program_id": programs[0].id,
            },
            {
                "name": "Department + Level",
                "department_id": department.id,
                "employee_level_id": level.id,
                "program_id": programs[1].id,
            },
            {
                "name": "Job + Level",
                "job_id": job.id,
                "employee_level_id": level.id,
                "program_id": programs[2].id,
            },
            {
                "name": "Job + Level + Role",
                "job_id": job.id,
                "employee_level_id": level.id,
                "role_track_id": role.id,
                "program_id": programs[3].id,
            },
        ])

        matched = self.Matrix._get_matching_matrices(employee)
        self.assertEqual(matched[:4], matrices[3] + matrices[2] + matrices[1] + matrices[0])
        self.assertEqual(self.Matrix._get_best_match_for_employee(employee), matrices[3])
