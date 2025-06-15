# PipeCondition

The `PipeCondition` operator enables routing in your pipeline based on conditional expressions. It evaluates an expression and routes the execution to different pipes based on the result.

## How It Works

1. **Expression Evaluation**:

   - Takes an input expression (either simple or Jinja2 template)
   - Evaluates it using the current working memory context
   - Returns a string value that determines which pipe to execute

2. **Pipe Selection**:

   - Uses a pipe map to match the evaluated expression to a target pipe
   - If no match is found, can use an optional default pipe

## Example: Product Type Router

```toml
[pipe.conditional_product_or_services]
PipeCondition = "Choose the correct pipe based on the product or services category"
inputs = { product_or_services_category = "ProductOrServicesCategory" }
output = "ProductOrService"
expression = "product_or_services_category.category"

[pipe.conditional_product_or_services.pipe_map]
product = "extract_product"
trips = "extract_trip"
public_transportation_subscription = "extract_public_transportation_subscription"
public_transportation_ticket = "extract_public_transportation_ticket"
other = "extract_other"
```

In this example:

1. The condition reads the `category` field from `product_or_services_category` in working memory
2. Based on the category value, it routes to a specific extraction pipe:
   - "product" → `extract_product`
   - "trips" → `extract_trip`
   - etc.

## Expression Types

### Simple Expression
```python
expression = "product_or_services_category.category"
```

- Direct access to working memory variables
- No template syntax needed
- Good for simple field access
- Access to Jinja2 filters and functions

## Features

### Default Routing
```python
default_pipe_code = "process_unknown"
```

- Fallback pipe when no match is found

### Expression Aliasing
```python
add_alias_from_expression_to = "category_type"
```

- Creates an alias from the expression result
- Makes the result available in working memory
