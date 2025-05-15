# Pipelex paradigm

Pipelex is a **Python framework** for **defining** and **running** **LLM-based knowledge pipelines** with high **reliability** and **replicability**.

As an **LLM scaffolding middleware**, Pipelex introduces relevant mechanisms to leverage the capabilities of these ai models while ensuring their **production readiness.**

**_Before going further with Pipelex, we suggest you have a look at the most important mechanisms._**

## TLDR

The Pipelex framework **processes knowledge through pipelines**, which consist of **sequential knowledge processing units called pipes**. Pipes access other pipes' outputs via the **Working Memory** system, making **processed knowledge available throughout the pipeline**. To ensure **reliability**, we implement **deterministic validation**: all pipe inputs and outputs (defined as Stuffs) **conform to specific concepts defined by the user (or by AI)**.

## Knowledge

Knowledge refers to information **extracted**, **processed**, or **organized** from various data sources such as documents, PDFs, images, or information output by our pipelines. It has been structured in a way that enables **understanding**, **interpretation**, and **actionable insights**.

## Pipeline

A pipeline is the Pipelex term for "Workflow". **It aims at processing knowledge using organized, consistent, validated steps.**

![Schema explaining a Pipelex pipeline](pipeline.png)

:bulb: **Remember the Quick-start chapter?** We defined a pipeline (in toml, using the [pipe] section) to generate a character!

## Pipe

A pipe is an **elementary step in a pipeline**. A pipeline is made of pipes.
Each pipe can integrate **both LLM-based** or software-based knowledge processing.

![Schema explaining a Pipelex elementary pipe](pipe.png)

:bulb: **Remember the Quick-start chapter?** We defined a pipe (in toml, using the [pipe.create_character] section) to generate a character. This was a very short pipeline as it comprised only one pipe.

## Working Memory

A pipe has access to all inputs as well as all the knowledge that was processed along the pipeline: **everything is stored in the Pipeline's Working Memory**. So can then **use all that stuff at any point in the pipeline.**

![*Working Memory: Pipe C can use Pipe A and Pipe B outputs. Pipe D can use Pipe C and Pipe B outputs, Pipe E …*](working_memory.png)
_Working Memory: Pipe C can use Pipe A and Pipe B outputs. Pipe D can use Pipe C and Pipe B outputs, Pipe E …_

:bulb: **Remember the Quick-start chapter?** We used the working memory to store a character before processing it (and extract metadata from it).

## Concepts

A concept **defines** **what is processed** through pipes.

**Rigorous concept definitions are the key to ensure controlled, reliable outputs.**

Concepts are defined both with **natural language** (so non-developer and LLM can understand and write them) and **with code** (to validate them deterministically with software).

Pipes embed **validation** of their outputs, so **we make sure of the knowledge we process and produce**.

![Schema explaining structured output validation](output_validation.png)


:bulb: **Remember the Quick-start chapter?** We defined a `Character` concept and a `CharacterMetadata` concept (in toml, using the [concept] section and with Python BaseModels) to define the input and output of the pipe!

:bulb: Soon we will also add input validation for pipes.


## Stuff

On the code side, **when a concept is instantiated** (to be processed or added to the working memory), **we call it a Stuff**.

:arrow_left: [**Back to Quick-start**](../Quick-start/Quick-start.md)

:arrow_right: [**Next section: Libraries**](../Libraries/libraries.md)

---

"Pipelex" is a trademark of Evotis S.A.S.

© 2025 Evotis S.A.S.
