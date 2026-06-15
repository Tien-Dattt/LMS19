# Codex Project Context

## Official Sources

Use only these documents as the business/specification source of truth:

- `02_SRS_MVP_Corporate_LMS_Odoo19_AI_Source_Aligned(1).md`
- `03_UML_Class_UseCase_MVP_Corporate_LMS_Odoo19_AI_Source_Aligned(1).md`

Do not use older SRS/UML versions. If a requirement is unclear, choose the simplest implementation that matches these two documents.

## Core Odoo Mapping

- Course = `slide.channel`
- Lesson/Slide = `slide.slide`
- Course membership/progress = `slide.channel.partner`
- Lesson progress = `slide.slide.partner`
- Odoo quiz core = `slide.question` / `slide.answer`
- AI/RAG = `ai.agent`, `ai.agent.source`, `ai.embedding`

## Non-Negotiable Constraints

- Do not modify Odoo core directly.
- Do not create replacement course, lesson, progress, RAG, or chatbot systems.
- Use Odoo eLearning membership APIs for enrollment, preferably `slide.channel._action_add_members(partners)`.
- Do not use Survey as a normal quiz; Survey is only for certification/survey flows.
- AI must not decide official score, pass/fail, certificate, permissions, or learner access.
- AI-generated content must remain draft/helper content until reviewed by an authorized user.
- Do not treat `viewed` as equivalent to `completed`.

## Current Phase Status

- Phases 1-14 are completed and tested.
- Last known full upgrade/test result: 79 tests, 0 failed, 0 errors.
- Phase 15 is next.
- Do not implement a later phase unless explicitly requested.

## Module Structure

- `corporate_lms_base`
- `corporate_lms_assessment`
- `corporate_lms_ai`

## Testing Policy

- Use the existing fixed database: `demo_odoo19_vibe_test`.
- All Odoo commands must include: `-c D:\Odoo\conf\Job_odoo19.conf -d demo_odoo19_vibe_test`.
- Never create or drop PostgreSQL databases unless explicitly approved.
- If PostgreSQL connection/authentication errors appear, stop and report an environment failure.
- Prefer static checks first, then targeted tests, then full upgrade/test when the phase is complete.
- Do not use `--without-demo=all` in Odoo 19.

## Future Workflow

- Implement one phase at a time.
- Read only the relevant files and relevant parts of the official documents for the current phase.
- Keep changes scoped and preserve existing code unless it conflicts with the official documents.
- Run targeted tests first, then the full upgrade/test when the phase is complete.
- Stop after each phase and report concise results.
