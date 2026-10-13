from typing import Any, ClassVar


class InvocationPathsTestData:
    """The worked example of the hosted progress contract, with leaves that run without a model.

    `filings.review_filings` is a sequence of four steps: a condition whose `detailed` outcome runs a parallel of two
    branches, then a step batched over the filings, whose items each run a sequence of two steps. Beyond the worked
    example, the condition maps a second key to `deep_checks`, which joins that group, and a key holding a space and a
    `/` to `legal_check`, whose segment percent-encodes it.
    """

    DOMAIN: ClassVar[str] = "filings"
    ENTRY_PATH: ClassVar[str] = "filings.review_filings"
    BUNDLE: ClassVar[str] = """
domain = "filings"
description = "Review a set of filings"
main_pipe = "review_filings"

[concept.Filing]
description = "A filing"

[concept.Filing.structure]
title = { type = "text", description = "The filing's title", required = true }

[concept.Dossier]
description = "The filings under review"

[concept.Dossier.structure]
filings = { type = "list", item_type = "concept", item_concept_ref = "Filing", description = "The filings", required = true }

[pipe.review_filings]
type = "PipeSequence"
description = "Extract the filings, check them at the depth asked, summarize each, report"
inputs = { dossier = "Dossier", depth = "Text" }
output = "Text"
steps = [
  { pipe = "extract_filings", result = "extracted" },
  { pipe = "choose_depth", result = "checks" },
  { pipe = "summarize_filing", batch_over = "dossier.filings", batch_as = "filing", result = "summaries" },
  { pipe = "assemble_report", result = "report" },
]

[pipe.extract_filings]
type = "PipeCompose"
description = "Extract the filings"
inputs = { depth = "Text" }
output = "Text"
template = "Extracted for a {{ depth }} review"

[pipe.choose_depth]
type = "PipeCondition"
description = "Check the filings in depth, quickly, or for the legal and tax questions"
inputs = { depth = "Text" }
output = "Anything"
expression = "depth"
outcomes = { detailed = "deep_checks", quick = "quick_check", "high risk" = "deep_checks", "legal/tax review" = "legal_check" }
default_outcome = "quick_check"

[pipe.deep_checks]
type = "PipeParallel"
description = "Check the figures and the wording at once"
inputs = { depth = "Text" }
output = "Composite"
branches = [
  { pipe = "check_figures", result = "figures" },
  { pipe = "check_wording", result = "wording" },
]

[pipe.check_figures]
type = "PipeCompose"
description = "Check the figures"
inputs = { depth = "Text" }
output = "Text"
template = "Figures checked for a {{ depth }} review"

[pipe.check_wording]
type = "PipeCompose"
description = "Check the wording"
inputs = { depth = "Text" }
output = "Text"
template = "Wording checked for a {{ depth }} review"

[pipe.quick_check]
type = "PipeCompose"
description = "Skim the filings"
inputs = { depth = "Text" }
output = "Text"
template = "Skimmed for a {{ depth }} review"

[pipe.legal_check]
type = "PipeCompose"
description = "Check the legal and tax questions"
inputs = { depth = "Text" }
output = "Text"
template = "Legal and tax questions checked for a {{ depth }} review"

[pipe.summarize_filing]
type = "PipeSequence"
description = "Read a filing, then condense it"
inputs = { filing = "Filing" }
output = "Text"
steps = [
  { pipe = "read_filing", result = "reading" },
  { pipe = "condense_filing", result = "summary" },
]

[pipe.read_filing]
type = "PipeCompose"
description = "Read a filing"
inputs = { filing = "Filing" }
output = "Text"
template = "Read {{ filing.title }}"

[pipe.condense_filing]
type = "PipeFunc"
description = "Condense the reading of a filing"
inputs = { reading = "Text" }
output = "Text"
function_name = "invocation_paths_condense_filing"

[pipe.assemble_report]
type = "PipeCompose"
description = "Assemble the report"
inputs = { extracted = "Text", summaries = "Text[]" }
output = "Text"
template = "{{ extracted }} / {{ summaries }}"
"""

    DOSSIER: ClassVar[dict[str, Any]] = {"filings": [{"title": "Annual accounts"}, {"title": "Board minutes"}, {"title": "Tax return"}]}

    # The paths of a live run over the three filings whose condition took `detailed`, as the worked example gives
    # them: by path, the code and the type of the pipe run there.
    LIVE_DETAILED_PATHS: ClassVar[dict[str, tuple[str, str]]] = {
        "filings.review_filings": ("review_filings", "PipeSequence"),
        "filings.review_filings/step_1": ("extract_filings", "PipeCompose"),
        "filings.review_filings/step_2": ("choose_depth", "PipeCondition"),
        "filings.review_filings/step_2/outcome_detailed": ("deep_checks", "PipeParallel"),
        "filings.review_filings/step_2/outcome_detailed/branch_1": ("check_figures", "PipeCompose"),
        "filings.review_filings/step_2/outcome_detailed/branch_2": ("check_wording", "PipeCompose"),
        "filings.review_filings/step_3": ("summarize_filing_batch", "PipeBatch"),
        "filings.review_filings/step_3/item_1": ("summarize_filing", "PipeSequence"),
        "filings.review_filings/step_3/item_1/step_1": ("read_filing", "PipeCompose"),
        "filings.review_filings/step_3/item_1/step_2": ("condense_filing", "PipeFunc"),
        "filings.review_filings/step_3/item_2": ("summarize_filing", "PipeSequence"),
        "filings.review_filings/step_3/item_2/step_1": ("read_filing", "PipeCompose"),
        "filings.review_filings/step_3/item_2/step_2": ("condense_filing", "PipeFunc"),
        "filings.review_filings/step_3/item_3": ("summarize_filing", "PipeSequence"),
        "filings.review_filings/step_3/item_3/step_1": ("read_filing", "PipeCompose"),
        "filings.review_filings/step_3/item_3/step_2": ("condense_filing", "PipeFunc"),
        "filings.review_filings/step_4": ("assemble_report", "PipeCompose"),
    }

    # Where each pipe of the condition runs, whichever outcome a live run takes and in a dry run, which runs them all.
    OUTCOME_GROUP_PATHS: ClassVar[dict[str, str]] = {
        "deep_checks": "filings.review_filings/step_2/outcome_detailed",
        "quick_check": "filings.review_filings/step_2/outcome_quick",
        "legal_check": "filings.review_filings/step_2/outcome_legal%2Ftax%20review",
    }

    # A sequence whose author wrote a binding step: the binding runs no pipe, and takes the number of the step it is.
    BOUND_STEP_BUNDLE: ClassVar[str] = """
domain = "bound_steps"
description = "Label a filing by its title"
main_pipe = "label_filing"

[concept.Filing]
description = "A filing"

[concept.Filing.structure]
title = { type = "text", description = "The filing's title", required = true }

[pipe.label_filing]
type = "PipeSequence"
description = "Bind the filing's title, then label the filing with it"
inputs = { filing = "Filing" }
output = "Text"
steps = [
  { from = "filing.title", result = "title" },
  { pipe = "write_label", result = "label" },
]

[pipe.write_label]
type = "PipeCompose"
description = "Write the label"
inputs = { title = "Text" }
output = "Text"
template = "Label: {{ title }}"
"""
