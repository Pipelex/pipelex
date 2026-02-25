# Pipelex (MTHDS) – Declarative AI Method Spec (v0.1.0)

**Build deterministic, repeatable AI methods using declarative TOML syntax.**

The Pipelex Language (MTHDS) uses a TOML-based syntax to define deterministic, repeatable AI methods. This specification documents version 0.1.0 of the language and establishes the canonical way to declare domains, concepts, and pipes inside `.mthds` bundles.

---

## Core Idea

Pipelex is a method declaration language that gets interpreted at runtime, we already have a Python runtime (see [github.com/pipelex/pipelex](https://github.com/pipelex/pipelex)).

Pipelex lets you declare **what** your AI method should accomplish and **how** to execute it step by step. Each `.mthds` file represents a bundle where you define:

- **Concepts** (PascalCase): the structured or unstructured data flowing through your system
- **Pipes** (snake_case): operations or orchestrators that define your method
- **Domain** (named in snake_case): the topic or field of work this bundle is about

Write once in `.mthds` files. Run anywhere. Get the same results every time.

---

## Semantics

Pipelex methods are **declarative and deterministic**:

- Pipes are evaluated based on their dependencies, not declaration order
- Controllers explicitly define execution flow (sequential, parallel, or conditional)

All concepts are strongly typed. All pipes declare their inputs and outputs. The runtime validates that data flowing between pipes matches the declared types before execution. Concepts are also conceptually defined, adding meaning on top of the technical typing.

---

## Guarantees & Limits

**Guarantees:**

- Deterministic method execution and outputs
- Strong typing with validation before runtime

**Not supported in v0.1.0:**

- Pipe namespaces per domain

**More:**

- GitHub: [github.com/pipelex/pipelex](https://github.com/pipelex/pipelex)

---

## Complete Example: CV Job Matching Method

This method analyses candidate CVs against job offer requirements to determine match quality.

```toml
domain = "cv_job_matching"
description = "Analyzing candidate CVs against job offer requirements to determine match quality."
main_pipe = "analyze_cv_job_matches"

[concept.JobRequirements]
description = "Structured representation of a job position's requirements and details."

[concept.JobRequirements.structure]
role_title = { type = "text", description = "The job title or position name", required = true }
key_responsibilities = { type = "text", description = "Main duties and responsibilities of the role", required = true }
required_qualifications = { type = "text", description = "Mandatory qualifications, skills, or experience needed", required = true }
preferred_qualifications = { type = "text", description = "Nice-to-have qualifications, skills, or experience" }
experience_level = { type = "text", description = "Required years or level of experience" }
technical_skills = { type = "text", description = "Specific technical skills or tools required" }
soft_skills = { type = "text", description = "Interpersonal or behavioral skills desired" }

[concept.CvMatchAnalysis]
description = "Assessment of how well a candidate's CV matches job requirements."

[concept.CvMatchAnalysis.structure]
overall_match_score = { type = "number", description = "Numerical score representing overall fit (0-100)", required = true }
strengths = { type = "text", description = "Areas where the candidate excels or meets requirements well", required = true }
weaknesses = { type = "text", description = "Areas where the candidate falls short or lacks requirements", required = true }
recommendation = { type = "text", description = "Final recommendation on whether to proceed with the candidate", required = true }
relevant_experience = { type = "text", description = "Summary of candidate's relevant work experience" }
skills_match = { type = "text", description = "Analysis of how candidate's skills align with job requirements" }

[pipe.analyze_cv_job_matches]
type = "PipeSequence"
description = """
Main pipeline that extracts job requirements from the job offer PDF and analyzes all candidate CVs against those requirements to determine match quality.
"""
inputs = { job_offer_pdf = "PDF", cv_pdfs = "PDF[]" }
output = "CvMatchAnalysis[]"
steps = [
    { pipe = "extract_job_offer", result = "job_offer_pages" },
    { pipe = "structure_job_requirements", result = "job_requirements" },
    { pipe = "process_all_cvs", result = "cv_match_analyses" },
]

[pipe.extract_job_offer]
type = "PipeExtract"
description = "Extracts text content from the job offer PDF document into pages."
inputs = { job_offer_pdf = "PDF" }
output = "Page[]"
model = "@default-text-from-pdf"

[pipe.structure_job_requirements]
type = "PipeLLM"
description = """
Consolidates all pages from the job offer into a single structured job description with key requirements, qualifications, and responsibilities.
"""
inputs = { job_offer_pages = "Page[]" }
output = "JobRequirements"
model = "$retrieval"
system_prompt = """
You are an expert HR analyst specializing in extracting and structuring job requirements from job postings. Your task is to produce a structured JobRequirements object based on the provided job offer document.
"""
prompt = """
Analyze the following job offer pages and extract the key information into a structured format.

@job_offer_pages

Extract and organize the job requirements, including the role title, key responsibilities, required and preferred qualifications, experience level, technical skills, and soft skills.
"""

[pipe.process_all_cvs]
type = "PipeBatch"
description = "Processes each CV PDF concurrently to extract and analyze against job requirements."
inputs = { cv_pdfs = "PDF[]", job_requirements = "JobRequirements" }
output = "CvMatchAnalysis[]"
branch_pipe_code = "process_single_cv"
input_list_name = "cv_pdfs"
input_item_name = "cv_pdf"

[pipe.process_single_cv]
type = "PipeSequence"
description = "Processes a single CV through extraction and analysis against job requirements."
inputs = { cv_pdf = "PDF", job_requirements = "JobRequirements" }
output = "CvMatchAnalysis"
steps = [
    { pipe = "extract_cv_content", result = "cv_pages" },
    { pipe = "analyze_cv_match", result = "cv_match_analysis" },
]

[pipe.extract_cv_content]
type = "PipeExtract"
description = "Extracts text content from a single CV PDF into pages."
inputs = { cv_pdf = "PDF" }
output = "Page[]"
model = "@default-text-from-pdf"

[pipe.analyze_cv_match]
type = "PipeLLM"
description = """
Analyzes the CV content against the job requirements and produces a match assessment with scores, strengths, weaknesses, and overall recommendation.
"""
inputs = { cv_pages = "Page[]", job_requirements = "JobRequirements" }
output = "CvMatchAnalysis"
model = "$engineering-structured"
system_prompt = """
You are an expert HR analyst and recruiter. Your task is to analyze candidate CVs against job requirements and produce structured assessments. Be thorough, objective, and provide actionable insights.
"""
prompt = """
Analyze the following CV against the job requirements and provide a comprehensive match assessment.

@cv_pages

Job Requirements:
- Role: $job_requirements.role_title
- Key Responsibilities: $job_requirements.key_responsibilities
- Required Qualifications: $job_requirements.required_qualifications
- Preferred Qualifications: $job_requirements.preferred_qualifications
- Experience Level: $job_requirements.experience_level
- Technical Skills: $job_requirements.technical_skills
- Soft Skills: $job_requirements.soft_skills

Evaluate how well this candidate matches the job requirements.
"""
```

**What happens:**

- Extracts and structures job requirements from a job offer PDF using document extraction + LLM
- Processes all candidate CVs in parallel (batch processing)
- Each CV is extracted and analyzed against the structured job requirements using an LLM
- Produces a scored match analysis for each candidate with strengths, weaknesses, and hiring recommendations
- Demonstrates sequential orchestration, parallel processing, nested methods, and strong typing

