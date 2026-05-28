# Resume JSON Format Rules

## Required Top-Level Fields

```json
{
  "company": "",
  "position": "",
  "skills": []
}
```

**`company`** (string, required) - Company name for folder organization  
**`position`** (string, required) - Job title  
**`skills`** (array, required) - Skill categories and items

---

## Bullet Section Format

Bullet sections are optional arrays of strings:

```json
"goose_bullets": [
  "Bullet point one.",
  "Bullet point two."
]
```

Supported sections:
- `goose_bullets` — Goose Deterrent System project
- `peizo_bullets` — AFC Piezo-Actuator project (note spelling)
- `windturbine_bullets` — Wind Turbine Revitalization
- `mostardi_bullets` — Mostardi Platt work experience
- `greenway_bullets` — GreenWay Landscaping work experience

**Rules:**
### Projects
The following sections are considered projects:
- Goose Deterrent System
- AFC Piezo-Actuator
- Wind Turbine Revitalization

Project sections must follow these rules:
- Minimum bullets: 3
- Maximum bullets: 4
- Minimum bullet length: 160 characters
- Maximum bullet length: 210 characters

Project bullets should emphasize:
- technical depth
- engineering terminology
- ATS keyword density
- measurable system complexity
- hardware/software/process integration
- analysis, validation, manufacturing, or system architecture
- Use measurable metrics when they strengthen the bullet, such as frequencies, accuracy rates, voltage ranges, dimensions, inspection counts, system scale, test duration, coverage area, or hardware quantities
- Only include metrics that are relevant to the target job description and support the technical claim being made
- Do not force metrics into bullets if they make the bullet weaker, awkward, exaggerated, or unrelated to the role

The Goose Deterrent System should usually receive the strongest technical emphasis unless another project is significantly more aligned with the target role.

---

### Work Experience
The following sections are considered work experience:
- Mostardi Platt
- GreenWay Landscaping

Work experience sections must follow these rules:

#### Mostardi Platt
- Minimum bullets: 2
- Maximum bullets: 3

#### GreenWay Landscaping
- Exactly 2 bullets

All work experience bullets:
- Minimum bullet length: 120 characters
- Maximum bullet length: 160 characters

Work experience bullets should emphasize:
- operational responsibility
- technical troubleshooting
- reliability
- diagnostics
- maintenance
- leadership
- coordination
- compliance
- real-world engineering application
- Include operational or field metrics when useful, such as setup time, testing duration, equipment count, travel frequency, team size, inspection count, temperature range, stack height, or maintenance frequency
- Use metrics only when they add credibility, scale, or technical specificity to the bullet
---

## Strong Action Verbs

Designed, Developed, Integrated, Programmed, Analyzed, Tested, Validated, Built, Calibrated, Documented, Automated, Coordinated, Optimized, Evaluated, Calculated, Manufactured, Fabricated

Avoid: Helped with, Worked on, Responsible for, Learned about

---

## Skills Format

```json
"skills": [
  {
    "category": "Category Name",
    "skills": ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5", "Skill 6"]
  }
]
```

**Rules:**
- 3 categories recommended
- 3-6 skills per category
- Ordered by relevance to job type
- No soft skills (teamwork, communication)
- Match job posting language

## Skill Category Name Rules

- Skill category names must contain:
- Minimum: 1 word
- Maximum: 2 words

Examples:
- CAD & Design
- Manufacturing
- Embedded Systems
- Simulation
- Programming
- Electrical Systems

Avoid:
- Long descriptive category names
- ATS-stuffed category titles
- Titles longer than 3 words

---

## Valid JSON Example

```json
{
  "company": "Example Corp",
  "position": "Engineering Intern",
  "goose_bullets": [
    "Designed and integrated mechanical systems for autonomous platform deployment.",
    "Developed control algorithms for motor systems and real-time hardware operation."
  ],
  "windturbine_bullets": [
    "Analyzed turbine control systems and electrical infrastructure for operational analysis.",
    "Created technical documentation for equipment maintenance and long-term system reliability."
  ],
  "mostardi_bullets": [
    "Calibrated precision equipment and maintained system accuracy under field conditions.",
    "Coordinated with engineers to validate testing procedures and ensure operational compliance."
  ],
  "skills": [
    {
      "category": "CAD/Simulation",
      "skills": ["SolidWorks", "ANSYS", "AutoCAD", "MATLAB"]
    },
    {
      "category": "Programming",
      "skills": ["Python", "C++", "MATLAB"]
    },
    {
      "category": "Embedded Systems",
      "skills": ["ESP32", "Motor Control", "Sensor Integration", "I2C/SPI"]
    }
  ]
}
```

---

## Output Requirement

GPT must output **raw JSON only** — no markdown formatting, no explanations, no preamble.
