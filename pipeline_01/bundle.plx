domain = "candidate_screening"
description = """
Screening candidates by matching CVs against job requirements and generating interview questions or rejection emails
"""
main_pipe = "screen_candidates"

[concept.JobRequirements]
description = "Structured summary of the key requirements and qualifications needed for a job position."

[concept.JobRequirements.structure]
position_title = { type = "text", description = "The title of the job position", required = true }
required_skills = { type = "text", description = "List of essential skills needed for the role" }
preferred_qualifications = { type = "text", description = "Additional qualifications that are desirable but not mandatory" }
experience_level = { type = "text", description = "Required years or level of experience" }
responsibilities = { type = "text", description = "Main duties and responsibilities of the role" }

[concept.MatchAnalysis]
description = "Assessment of how well a candidate's profile aligns with job requirements."

[concept.MatchAnalysis.structure]
match_decision = { type = "boolean", description = "Whether the candidate matches the job requirements", required = true }
reasoning = { type = "text", description = "Explanation of why the candidate does or does not match", required = true }
match_score = { type = "number", description = "Numerical score representing the quality of the match" }

[concept.InterviewQuestion]
description = "A single question designed to assess a candidate during an interview."

[concept.InterviewQuestion.structure]
question_text = { type = "text", description = "The actual question to be asked", required = true }
purpose = { type = "text", description = "What aspect of the candidate or role this question evaluates" }
category = { type = "text", description = "The type or category of question (e.g., technical, behavioral, situational)" }

[concept.RefusalEmail]
description = "A professional email declining a candidate's application."
refines = "Text"

[pipe.screen_candidates]
type = "PipeSequence"
description = """
Main pipeline orchestrator that extracts job requirements and screens all candidate CVs against the job offer
"""
inputs = { job_offer_pdf = "PDF", cv_pdfs = "PDF[]" }
output = "Text[]"
steps = [
    { pipe = "extract_job_offer", result = "job_offer_pages" },
    { pipe = "structure_job_requirements", result = "job_requirements" },
    { pipe = "process_all_cvs", result = "screening_results" },
]

[pipe.extract_job_offer]
type = "PipeExtract"
description = "Extracts text content from the job offer PDF document"
inputs = { job_offer_pdf = "PDF" }
output = "Page[]"
model = "extract_text_from_pdf"

[pipe.structure_job_requirements]
type = "PipeLLM"
description = "Analyzes job offer pages and consolidates them into structured job requirements"
inputs = { job_offer_pages = "Page" }
output = "JobRequirements"
model = "llm_to_retrieve"
system_prompt = """
You are an expert HR analyst specializing in extracting and structuring job requirements from job offer documents. Your task is to produce a structured JobRequirements object.
"""
prompt = """
Analyze the following job offer pages and extract the key job requirements into a structured format.

@job_offer_pages

Extract and organize the information about the position title, required skills, preferred qualifications, experience level, and main responsibilities.
"""

[pipe.process_all_cvs]
type = "PipeBatch"
description = "Applies CV processing pipeline to each CV in the batch"
inputs = { cv_pdfs = "PDF[]", job_requirements = "JobRequirements" }
output = "Text[]"
branch_pipe_code = "process_single_cv"
input_list_name = "cv_pdfs"
input_item_name = "cv_pdf"

[pipe.process_single_cv]
type = "PipeSequence"
description = "Processes a single CV through extraction, analysis, and conditional routing"
inputs = { cv_pdf = "PDF", job_requirements = "JobRequirements" }
output = "native.Anything"
steps = [
    { pipe = "extract_cv", result = "cv_pages" },
    { pipe = "analyze_cv_match", result = "match_analysis" },
    { pipe = "route_by_match_decision", result = "cv_outcome" },
]

[pipe.extract_cv]
type = "PipeExtract"
description = "Extracts text content from a single CV PDF document"
inputs = { cv_pdf = "PDF" }
output = "Page[]"
model = "extract_text_from_pdf"

[pipe.analyze_cv_match]
type = "PipeLLM"
description = "Evaluates how well the candidate's CV matches the job requirements"
inputs = { cv_pages = "Page", job_requirements = "JobRequirements" }
output = "MatchAnalysis"
model = "llm_to_answer_questions"
system_prompt = """
You are an expert HR analyst specializing in candidate evaluation. Your task is to produce a structured assessment of candidate-job fit.
"""
prompt = """
Analyze the following CV against the job requirements and assess whether the candidate is a good match for the position.

@cv_pages

@job_requirements

Evaluate the candidate's qualifications, skills, experience, and background against the job requirements. Determine whether they meet the essential criteria and would be suitable for the role.
"""

[pipe.route_by_match_decision]
type = "PipeCondition"
description = "Routes the workflow based on whether the candidate matches job requirements"
inputs = { match_analysis = "MatchAnalysis", cv_pages = "Page", job_requirements = "JobRequirements" }
output = "native.Anything"
expression_template = "{{ match_analysis.match_decision }}"
outcomes = { True = "generate_interview_questions", False = "write_refusal_email" }
default_outcome = "fail"

[pipe.generate_interview_questions]
type = "PipeLLM"
description = "Creates 5 tailored interview questions for matched candidates"
inputs = { cv_pages = "Page", job_requirements = "JobRequirements", match_analysis = "MatchAnalysis" }
output = "InterviewQuestion[5]"
model = "llm_for_creative_writing"
system_prompt = """
You are an expert HR professional and interviewer. Your task is to generate structured InterviewQuestion objects that are tailored, insightful, and relevant to both the candidate's profile and the job requirements.
"""
prompt = """
Based on the candidate's CV and the job requirements, generate exactly 5 tailored interview questions that will help assess this candidate's fit for the position.

@cv_pages

@job_requirements

@match_analysis

Create questions that:
- Probe specific experiences or skills mentioned in the CV that are relevant to the job
- Address the key requirements and responsibilities of the position
- Build on the strengths identified in the match analysis
- Include a mix of technical, behavioral, and situational questions
- Are open-ended and encourage detailed responses
"""

[pipe.write_refusal_email]
type = "PipeLLM"
description = "Composes a professional rejection email for non-matching candidates"
inputs = { cv_pages = "Page", job_requirements = "JobRequirements", match_analysis = "MatchAnalysis" }
output = "RefusalEmail"
model = "llm_for_writing_cheap"
system_prompt = """
You are a professional HR communication specialist. Your task is to compose a polite, respectful, and professional rejection email for job candidates. The email should be empathetic while clearly communicating the decision. You will generate a structured RefusalEmail.
"""
prompt = """
Write a professional rejection email for a candidate who applied for the position.

@cv_pages

@job_requirements

@match_analysis

The email should:
- Be respectful and empathetic
- Thank the candidate for their interest and time
- Clearly communicate that they were not selected
- Be professional and maintain a positive tone
- Wish them well in their future endeavors
- Keep a reasonable length (not too brief, not too lengthy)
"""
