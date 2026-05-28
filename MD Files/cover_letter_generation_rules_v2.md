# Cover Letter Generation Rules

## Workflow Context

This file guides GPT to generate a cover letter **after the resume has been created**. 

Input: Job description + Generated Resume JSON (or text) + This rules file
Output: Cover letter JSON (raw, downloadable file only—no chat explanations)

---

## Output Requirement

GPT must generate **valid JSON as a downloadable file only**.

Never output raw JSON into chat, include markdown formatting, code fences, explanations, or commentary.

---

## Required JSON Fields

```json
{
  "company": "Company name from the job posting",
  "company_address": "Company address from posting or official website",
  "position": "Exact job title from the job posting",
  "technical_area_from_job": "Primary technical area or responsibility from the posting",
  "your_project_that_matches": "Main project from resume that aligns with the role",
  "specific_challenge_you_solved": "Specific technical challenge encountered on that project",
  "what_you_did": "Technical solution, analysis, or implementation performed",
  "quantifiable_outcome": "Measured or observable result from the solution",
  "skill_from_job": "Technical skill developed that directly matches the role",
  "previous_job_title": "Most relevant work experience title from resume",
  "work_experience_lesson": "Operational or technical discipline learned from prior work",
  "why_this_company_unique": "Truthful, company-specific reason for interest",
  "logistics_requirement": "Operational expectation (travel, fieldwork, testing, teamwork, etc.)"
}
```

---

## Voice & Language Rules

**Tone:** Professional, direct, technically grounded, confident without exaggeration. Written for an engineering student applicant.

**Priority Order:**
1. Technical accuracy and ATS keyword alignment
2. Natural sentence flow
3. Concise engineering language
4. Realistic student-level experience

**Do NOT use:**
- "passionate about," "dream company," "always wanted to," "cutting-edge," "fast-paced," "team player," "hardworking"
- Motivational or corporate buzzwords
- Do not imply deep insider knowledge or long-term familiarity with the company
- Vague claims or filler wording
- Excessive enthusiasm or exaggeration

**Do:**
- Mirror technical terminology from the job posting
- Use discipline-specific wording from the resume
- Reference only projects and experience that exist in the resume
- Keep rendered letter under ~one page
- Keep each placeholder concise and insertion-ready; typically 4–18 words unless otherwise specified
- Sound realistic for a student engineer

---

## Placeholder Construction Rules

**Golden Rule:** Each field generates insertion-ready text fragments that fit grammatically into a pre-written template.

Outputs must:
- Fit smoothly into surrounding sentence structure
- Remain concise (avoid full paragraphs or unnecessary transitions)
- Avoid repeating information elsewhere in the letter
- Avoid repeating the same technical concepts across multiple placeholder fields unless necessary for sentence clarity
- Flow naturally when inserted

---

## Placeholder-by-Placeholder Rules

### `company` (Max: 4 words)
**Template:** "I'm specifically excited about {{ company }} because..."
- Exact company name from posting
- Do not abbreviate unless official

### `position` (Max: 8 words)
**Template:** "When I saw the opening for the {{ position }}, ..."
- Exact title from posting, consistent capitalization

### `technical_area_from_job` (Max: 8 words)
**Template:** "...the role's focus on {{ technical_area_from_job }} strongly aligns..."
- Short engineering area/responsibility phrase (not full sentence)
- Keep technical, avoid excessive modifiers
- **Good:** "embedded motor control systems" | **Bad:** "working with embedded systems in fast-paced environments"

### `your_project_that_matches` (Max: 5 words)
**Template:** "...the work I've done on {{ your_project_that_matches }}."
- Project title only, no description
- **Good:** "Goose Deterrent System" | **Bad:** "my embedded systems goose project"

### `specific_challenge_you_solved` (Max: 14 words)
**Template:** "On {{ your_project_that_matches }}, I ran into {{ specific_challenge_you_solved }}."
- Concise technical challenge phrase (not full sentence)
- Do not begin with a verb; must follow "ran into" grammatically
- **Good:** "low-latency motor synchronization issues during real-time tracking" | **Bad:** "I solved motor synchronization problems"

### `what_you_did` (Max: 18 words)
**Template:** "I solved it by {{ what_you_did }}, which resulted in..."
- Must begin with verb ending in "-ing"
- Describe implemented solution only, avoid unnecessary detail
- **Good:** "optimizing the motor control pipeline and restructuring hardware-firmware communication" | **Bad:** "I redesigned the system to improve reliability"

### `quantifiable_outcome` (Max: 14 words)
**Template:** "...which resulted in {{ quantifiable_outcome }}."
- Measurable or observable improvement (prefer metrics from resume)
- Must follow "resulted in" grammatically
- **Good:** "increasing targeting precision from feet-level to several-inch accuracy" | **Bad:** "better system performance"

### `skill_from_job` (Max: 10 words)
**Template:** "That experience taught me how to {{ skill_from_job }} under real constraints."
- Begin with a verb, grammatically follows "how to"
- Avoid repeating technical_area_from_job directly
- **Good:** "optimize embedded motor control systems" | **Bad:** "real-time embedded systems"

### `previous_job_title` (Max: 4 words)
**Template:** "...my time as a {{ previous_job_title }} taught me..."
- Exact work title only, no description
- **Good:** "Air Emissions Engineer" | **Bad:** "engineer at an environmental company"

### `work_experience_lesson` (Max: 14 words)
**Template:** "...taught me {{ work_experience_lesson }}."
- Grammatically follows "taught me"
- Describe concise professional capability, avoid soft-skill language
- **Good:** "maintain precision during long-duration industrial field testing" | **Bad:** "the importance of teamwork"

### `why_this_company_unique` (Max: 18 words)
**Template:** "I'm specifically excited about {{ company }} because {{ why_this_company_unique }}."
- Grammatically follows "because" (do not begin with "because")
- Concise, technically grounded, no marketing language or exaggeration
- Use only official company website, job posting, or reputable public info
- Do not invent internal projects, initiatives, or teams
- **Good:** "of your work in precision industrial equipment and system reliability" | **Bad:** "you are an innovative industry leader"

### `logistics_requirement` (Max: 10 words)
**Template:** "I understand this role involves {{ logistics_requirement }}, and I'm fully prepared..."
- Short operational phrase (not full sentence)
- **Good:** "hands-on testing and collaborative engineering work" | **Bad:** "working in teams to solve engineering problems"

---

## Company Research Rules

Use only:
- Official company website
- Official job posting
- Reputable public company information

Do NOT invent:
- Internal projects, initiatives, or engineering teams
- Technical responsibilities or product involvement
- Marketing language or exaggerated praise

If limited company information available: Use broad but truthful technical descriptions; prefer conservative wording.

---

## Summary

This rules file ensures cover letters are:
- **Technically accurate** (resume-grounded, no invented experience)
- **Grammatically precise** (insertion-ready text fragments)
- **Concise and professional** (no corporate buzzwords or exaggeration)
- **Realistic** (student-level, believable, based on actual experience)
