# The Pipelex Paradigm

Pipelex is an **open-source Python framework** for defining and running **repeatable AI workflows**.

Here's what we've learned: LLMs are powerful, but asking them to do everything in one prompt is like asking a brilliant colleague to solve ten problems while juggling. The more complexity you pack into a single prompt, the more reliability drops. You've seen it: the perfect prompt that works 90% of the time until it doesn't.

The solution is straightforward: break complex tasks into focused steps. But without proper tooling, you end up with spaghetti code and prompts scattered across your codebase.

Pipelex introduces **knowledge pipelines**: a way to capture these workflow steps as **composable pipes**. Each pipe follows one rule: **knowledge in, knowledge out**. Unlike rigid templates, each pipe uses AI's full intelligence to handle variation while guaranteeing consistent output structure. You get **deterministic structure with adaptive intelligence**, the reliability of software with the flexibility of AI.

## Working with Knowledge and Using Concepts to Make Sense

Knowledge refers to information you input from various data sources such as documents, PDFs, images, or information output by our pipes. There are different kinds of knowledge.

### From Data Types to Concepts

In traditional programming, we work with data types: strings, integers, booleans (true/false), etc. But **knowledge work operates at a higher level.** Take for instance a *"non-compete clause from a contract"* and a *"description of a flower"*: they're both text, both are stored as strings, but they represent fundamentally different concepts. You can ask an AI to extract the duration in months from a non-compete clause. You can ask an AI to render a flower description as a Monet-style painting. But if you try the reverse, it doesn't make sense.

This is why Pipelex introduces **Concepts: typing with meaning attached.**

**Thanks to Pipelex's conceptual level of abstraction, knowledge pipelines can guarantee they make sense.**

## How *Making Sense* Translates to *Reliability*

Concretely, in Pipelex, a piece of knowledge is an object in the working memory. It could be anything, so we call that "stuff", and our Python class for it is `Stuff`.

Stuff can be pretty basic, like plain text or an image, but it can also be structured with attributes, comprise lists, include other nested stuff, you get it... the stuff's content is actually a `Pydantic BaseModel`. Also, each Stuff knows what concept it belongs to, e.g., `Text` or `NonCompeteClause` or `FlowerDescription`.

And with that we are fully equipped for Lego-style plug-n-play:

- Each pipe declares what inputs it uses, indicating the expected concept(s)
- Each pipe also declares what it outputs

So when you connect two pipes, Pipelex systematically checks that they are compatible. Actually, it's even more powerful than that: imagine you have a sequence of 5 pipes, maybe pipe #4 takes two inputs, one given from the output of previous pipe #3 and the other one from the output of pipe #1. Pipelex checks that running the previous steps will have generated the required stuff and with the required concepts.

What if you have a pipe that requires a `Text` input, to translate it to Spanish for instance, then it should also accept a `FlowerDescription`, right? Yes, the greater includes the lesser. This is expressed in Pipelex by indicating that concept `FlowerDescription` **refines** concept `Text`.

One problem that developers face when working with LLMs is that LLMs always try to answer your queries, and it pushes them to hallucinate. For instance, if you're trying to extract structured purchase details from an invoice, and there's a bug in your system so instead of receiving an invoice as input, the LLM received a picture of a flower, or nothing at all, there's a good chance it will generate a 100% hallucinated mock invoice. Pipelex prevents this kind of bugs, first by making sure the pipeline makes sense a priori, but it can also check any input for compatibility with the expected concept.

**By letting you clearly assign concepts to the input and output stuff of your pipes, Pipelex makes sure that your pipeline makes sense, that it works in theory, and detects any failure of meaning at the earliest stage possible in practice.**

## Who Defines the Concepts?

***You* define *your* concepts!**

Apart from a few very basic concepts (`Text`, `Image`, etc.), you can and you should define the concepts you work with. And that's a big win: the concepts you define make up the glossary of the domain you are working on. That's where you remove any ambiguity, because the same word can mean different things, and even the same concept can imply different things in various settings.
