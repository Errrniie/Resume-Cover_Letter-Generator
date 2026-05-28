# Job Analysis Rules

**Purpose:** Analyze a job description to extract priorities, identify which resume projects/skills should be emphasized, and guide Step 2 (resume generation).

**This is Step 1 of a two-step process.**

Input: Job description only
Output: JSON analysis (non-downloadable, in-chat, for manual review)

---

## Analysis Task

Read the job description carefully. Extract and output ONLY valid JSON with the following structure:

```json
{
  "job_title": "exact job title from posting",
  "company": "company name",
  "primary_focus": "primary engineering discipline or responsibility (1-2 sentence summary)",
  "technical_priorities": [
    "priority 1: specific technical area or responsibility",
    "priority 2: specific technical area or responsibility",
    "priority 3: specific technical area or responsibility",
    "priority 4 (optional): specific technical area or responsibility",
    "priority 5 (optional): specific technical area or responsibility"
  ],
  "key_required_skills": [
    "skill 1 from job posting",
    "skill 2 from job posting",
    "skill 3 from job posting"
  ],
  "skills_to_front_load": [
    "skill 1 that matches job priorities",
    "skill 2 that matches job priorities",
    "skill 3 that matches job priorities"
  ],
  "skills_to_de_emphasize": [
    "skill 1 that doesn't match this role",
    "skill 2 that doesn't match this role"
  ],
  "tone_and_language": "brief description of how to frame experience (e.g., 'production-focused', 'research-oriented', 'documentation-heavy', 'field operations')",
  "curation_notes": "2-3 sentence explanation of the strategic emphasis: why emphasize these projects, what makes this role distinct, what should the resume prioritize"
}
```

---

## Extraction Rules

### `job_title`
- Use exact title from job posting
- Do not paraphrase or interpret

### `company`
- Exact company name from posting

### `primary_focus`
- Read the job description holistically
- Identify the core engineering discipline or responsibility
- Examples: "production CAD drafting and technical drawing generation," "manufacturing process control and quality documentation," "embedded motor control system design," "electrical power systems analysis"
- 1-2 sentences max

### `technical_priorities`
- Extract the top 3-5 specific responsibilities, technical areas, or deliverables from the job description
- Prioritize by frequency, emphasis, and job posting language
- Examples:
  - "CAD design and technical drawing production"
  - "dimensional specifications and material documentation"
  - "quality inspection and compliance testing"
  - "embedded motor control and real-time systems"
  - "PCB circuit design and custom fabrication"
- Do NOT list generic skills (e.g., "problem-solving")
- Be specific to this role's actual focus

### `key_required_skills`
- Extract explicitly required or strongly preferred skills from the posting
- Examples: "AutoCAD," "SolidWorks," "C++," "ANSYS," "Python," "quality inspection"
- List 3 most critical skills

### `skills_to_front_load`
- From the full resume skills list, identify 3-5 skills that directly match this job's technical priorities
- These should be the first skills listed in the resume output
- Example for CAD drafting role: SolidWorks, AutoCAD, Technical Drawings, Dimensional Inspection

### `skills_to_de_emphasize`
- Identify skills that are true but not relevant to this role
- Example for CAD drafting role: "real-time embedded systems," "aerodynamic analysis"
- These should be moved to secondary positions or minimized

### `tone_and_language`
- Briefly describe the professional tone and technical framing for this role
- Examples:
  - "production-focused: emphasize delivery, timelines, documentation accuracy"
  - "research-oriented: emphasize methodology, simulation, validation"
  - "field operations: emphasize hands-on troubleshooting, equipment reliability"
  - "documentation-heavy: emphasize technical drawing standards, compliance, revision control"

### `curation_notes`
- 2-3 sentence summary explaining your strategic curation
- Why these projects? What makes this role distinct from adjacent roles?
- What should the resume prioritize?
- Example: "This role is production-focused CAD drafting, not design engineering. Emphasize the Goose Deterrent's CAD and technical drawing work, Wind Turbine's documentation creation, and Mostardi Platt's precision and compliance. De-emphasize embedded systems and vision algorithms. Frame experience around drawing output, dimensional accuracy, and documentation delivery."

---

## Output Format

Output ONLY the JSON above. No markdown formatting, no explanations, no preamble or commentary.

The JSON will be copied back into the resume generator (Step 2) to guide project and skill curation.

---

## Step 2 Context (Reference Only)

After Step 1 completes:
1. User copies the JSON output from this analysis
2. User provides that JSON to Step 2 (Resume Generation) along with resume format rules and resume reference material
3. Step 2 uses the priorities to curate and reframe resume bullets, ensuring bullets are tailored to this specific job's focus
4. Step 2 outputs a downloadable resume JSON file
