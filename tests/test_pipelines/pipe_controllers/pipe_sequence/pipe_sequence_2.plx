domain = "customer_feedback"
description = "Processing customer reviews and feedback"
system_prompt = "You are an expert at analyzing customer feedback and sentiment"

[concept]
CustomerReview = "A single customer review text"
SentimentAnalysis = "Sentiment analysis result for a review"
ProductRating = "Overall product rating based on reviews"
Document = "A document containing multiple customer reviews"

[pipe]
[pipe.analyze_reviews_sequence]
type = "PipeSequence"
description = "Process customer reviews with sentiment analysis"
inputs = { document = "Document" }
output = "ProductRating"
steps = [
    { pipe = "extract_individual_reviews", result = "review_list" },
    { pipe = "analyze_review_sentiment", batch_over = "review_list", batch_as = "single_review", result = "sentiment_analyses" },
    { pipe = "aggregate_review_results", result = "product_rating" },
]

[pipe.extract_individual_reviews]
type = "PipeLLM"
description = "Extract individual reviews from document"
inputs = { document = "Document" }
output = "CustomerReview"
multiple_output = true
model = "llm_for_testing_gen_text"
prompt = """
Extract each individual customer review from this document as separate items:

@document
"""

[pipe.analyze_review_sentiment]
type = "PipeLLM"
description = "Analyze sentiment of a single review"
inputs = { single_review = "CustomerReview" }
output = "SentimentAnalysis"
model = "llm_for_testing_gen_text"
prompt = """
Analyze the sentiment of this customer review:

@single_review

Provide sentiment (positive/negative/neutral) and confidence score.
"""

[pipe.aggregate_review_results]
type = "PipeLLM"
description = "Aggregate all review analyses into final rating"
inputs = { sentiment_analyses = "SentimentAnalysis" }
output = "ProductRating"
model = "llm_for_testing_gen_text"
prompt = """
Based on these sentiment analyses, provide an overall product rating:

@sentiment_analyses

Give a rating from 1-5 stars with explanation.
"""

