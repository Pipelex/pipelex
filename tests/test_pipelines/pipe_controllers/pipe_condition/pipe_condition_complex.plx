domain = "test_pipe_condition_complex"
description = "Complex document processing pipeline with multiple inputs and nested PipeConditions"

[concept]
DocumentRequest = "Document processing request with type, priority, language, and complexity"
UserProfile = "User profile with level and department information"
ProcessingContext = "Combined processing context"

[pipe]
# Main entry point - routes by document type first
[pipe.complex_document_processor]
type = "PipeCondition"
description = "Primary routing by document type"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
expression_template = "{{ doc_request.document_type }}"

[pipe.complex_document_processor.pipe_map]
technical = "technical_document_router"
business = "business_document_router"
legal = "legal_document_router"

# Technical document processing branch
[pipe.technical_document_router]
type = "PipeCondition"
description = "Route technical documents by priority and user level"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
expression_template = "{% if doc_request.priority == 'urgent' %}urgent_tech{% elif user_profile.user_level == 'expert' and doc_request.complexity == 'high' %}expert_tech{% else %}standard_tech{% endif %}"

[pipe.technical_document_router.pipe_map]
urgent_tech = "urgent_technical_processor"
expert_tech = "expert_technical_processor"
standard_tech = "standard_technical_processor"

# Business document processing branch
[pipe.business_document_router]
type = "PipeCondition"
description = "Route business documents by department and priority"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
expression_template = "{% if doc_request.priority == 'urgent' %}urgent_business{% elif user_profile.department == 'finance' %}finance_business{% elif user_profile.department == 'marketing' %}marketing_business{% else %}general_business{% endif %}"

[pipe.business_document_router.pipe_map]
urgent_business = "urgent_business_processor"
finance_business = "finance_business_processor"
marketing_business = "marketing_business_processor"
general_business = "general_business_processor"

# Legal document processing branch
[pipe.legal_document_router]
type = "PipeCondition"
description = "Route legal documents by complexity and user level"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
expression_template = "{% if doc_request.complexity == 'high' and user_profile.user_level != 'beginner' %}complex_legal{% elif doc_request.language != 'english' %}international_legal{% else %}standard_legal{% endif %}"

[pipe.legal_document_router.pipe_map]
complex_legal = "complex_legal_processor"
international_legal = "international_legal_processor"
standard_legal = "standard_legal_processor"

# Leaf processors - Technical
[pipe.urgent_technical_processor]
type = "PipeLLM"
description = "Process urgent technical documents with high priority"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this urgent technical document with immediate attention.
@doc_request.document_type
@doc_request.priority
@doc_request.complexity
@user_profile.user_level
@user_profile.department

Output: "URGENT_TECHNICAL_PROCESSED"
"""

[pipe.expert_technical_processor]
type = "PipeLLM"
description = "Process complex technical documents for expert users"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this complex technical document for expert user.
@doc_request.document_type
@doc_request.complexity
@user_profile.user_level

Output: "EXPERT_TECHNICAL_PROCESSED"
"""

[pipe.standard_technical_processor]
type = "PipeLLM"
description = "Process standard technical documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this standard technical document.
@doc_request.document_type
@user_profile.user_level

Output: "STANDARD_TECHNICAL_PROCESSED"
"""

# Leaf processors - Business
[pipe.urgent_business_processor]
type = "PipeLLM"
description = "Process urgent business documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this urgent business document.
@doc_request.priority
@user_profile.department

Output: "URGENT_BUSINESS_PROCESSED"
"""

[pipe.finance_business_processor]
type = "PipeLLM"
description = "Process finance business documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this finance business document.
@user_profile.department
@doc_request.document_type

Output: "FINANCE_BUSINESS_PROCESSED"
"""

[pipe.marketing_business_processor]
type = "PipeLLM"
description = "Process marketing business documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this marketing business document.
@user_profile.department
@doc_request.language

Output: "MARKETING_BUSINESS_PROCESSED"
"""

[pipe.general_business_processor]
type = "PipeLLM"
description = "Process general business documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this general business document.
@doc_request.document_type
@user_profile.department

Output: "GENERAL_BUSINESS_PROCESSED"
"""

# Leaf processors - Legal
[pipe.complex_legal_processor]
type = "PipeLLM"
description = "Process complex legal documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this complex legal document.
@doc_request.complexity
@user_profile.user_level
@doc_request.language

Output: "COMPLEX_LEGAL_PROCESSED"
"""

[pipe.international_legal_processor]
type = "PipeLLM"
description = "Process international legal documents"
inputs = { doc_request = "DocumentRequest" }
output = "native.Text"
prompt_template = """
Process this international legal document.
@doc_request.language
@doc_request.document_type

Output: "INTERNATIONAL_LEGAL_PROCESSED"
"""

[pipe.standard_legal_processor]
type = "PipeLLM"
description = "Process standard legal documents"
inputs = { doc_request = "DocumentRequest", user_profile = "UserProfile" }
output = "native.Text"
prompt_template = """
Process this standard legal document.
@doc_request.document_type
@user_profile.user_level

Output: "STANDARD_LEGAL_PROCESSED"
"""

