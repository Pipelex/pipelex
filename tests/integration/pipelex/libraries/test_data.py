from typing import ClassVar


class InstalledNotesPackageTestData:
    """A consumer bundle and an installed method package it references by address; nothing here is real."""

    METHOD_NAME: ClassVar[str] = "notes"
    DEP_ALIAS: ClassVar[str] = "github.com/invented/notes-lib/notes"

    DEP_MANIFEST: ClassVar[str] = """[package]
name        = "notes"
address     = "github.com/invented/notes-lib"
version     = "1.0.0"
description = "An invented notes library"

[exports.invented_notes]
pipes = ["find_notes"]
"""

    #: The dependency's `NoteSearch` holds a list of its `Note`.
    DEP_BUNDLE: ClassVar[str] = """domain      = "invented_notes"
description = "An invented notes library"

[concept.Note]
description = "One invented note"

[concept.Note.structure]
title = { type = "text", description = "The note's title", required = true }

[concept.NoteSearch]
description = "The notes a search found"

[concept.NoteSearch.structure]
notes = { type = "list", item_type = "concept", item_concept_ref = "invented_notes.Note", description = "The notes found", required = true }

[pipe.find_notes]
type        = "PipeLLM"
description = "Find the notes about a query"
inputs      = { query = "Text" }
output      = "NoteSearch"
prompt      = "Find the notes about $query."
"""

    #: The same package, whose `Note` also names a concept of the package's own dependency, which is never loaded.
    DEP_BUNDLE_NAMING_ITS_OWN_DEPENDENCY: ClassVar[str] = """domain      = "invented_notes"
description = "An invented notes library that depends on another package"

[concept.Note]
description = "One invented note, citing a source from another package"

[concept.Note.structure]
title  = { type = "text", description = "The note's title", required = true }
source = { type = "concept", concept_ref = "github.com/invented/sources-lib/sources->invented_sources.Source", description = "Where it came from" }

[concept.NoteSearch]
description = "The notes a search found"

[concept.NoteSearch.structure]
notes = { type = "list", item_type = "concept", item_concept_ref = "invented_notes.Note", description = "The notes found", required = true }

[pipe.find_notes]
type        = "PipeLLM"
description = "Find the notes about a query"
inputs      = { query = "Text" }
output      = "NoteSearch"
prompt      = "Find the notes about $query."
"""

    #: The consumer's `Digest` has a field typed by the dependency's `Note`, and a field with choices, whose strings name
    #: no class. Its sequence steps into the dependency's pipe, which is what makes the loader discover the package: a
    #: concept ref alone does not (L-260929-9c8eac).
    CONSUMER_BUNDLE: ClassVar[str] = """domain      = "invented_consumer"
description = "A consumer of the invented notes library"

[concept.Digest]
description = "A digest built around one note"

[concept.Digest.structure]
note    = { type = "concept", concept_ref = "github.com/invented/notes-lib/notes->invented_notes.Note", description = "The note", required = true }
summary = { type = "text", description = "What the note says", required = true }
tone    = { choices = ["brief", "detailed"], description = "How long the digest runs" }

[pipe.digest_notes]
type        = "PipeSequence"
description = "Find the invented notes about a query, then digest them"
inputs      = { query = "Text" }
output      = "Digest"
steps       = [
  { pipe = "github.com/invented/notes-lib/notes->invented_notes.find_notes", result = "found_notes" },
  { pipe = "write_digest", result = "digest" },
]

[pipe.write_digest]
type        = "PipeLLM"
description = "Digest the notes found about a query"
inputs      = { query = "Text" }
output      = "Digest"
prompt      = "Digest the notes about $query."
"""


class ProbePackageTestData:
    """An installed method package whose sequence calls its own helper, and consumers of it; nothing here is real.

    The helpers' descriptions say whose they are, so a graph or a resolved pipe tells which one a call reached.
    """

    METHOD_NAME: ClassVar[str] = "probe"
    DEP_ALIAS: ClassVar[str] = "github.com/invented/probe-lib/probe"

    MANIFEST_EXPORTING_EVERYTHING: ClassVar[str] = """[package]
name        = "probe"
address     = "github.com/invented/probe-lib"
version     = "1.0.0"
description = "An invented probe package"

[exports.probe_dep]
pipes = ["entry", "helper"]
"""

    MANIFEST_EXPORTING_ONLY_THE_ENTRY: ClassVar[str] = """[package]
name        = "probe"
address     = "github.com/invented/probe-lib"
version     = "1.0.0"
description = "An invented probe package"

[exports.probe_dep]
pipes = ["entry"]
"""

    #: `entry` calls its own `helper` by bare code, the way a package is authored. `orphan` is reached by nothing,
    #: and names a model no deck defines, so building it would refuse.
    DEP_BUNDLE: ClassVar[str] = """domain      = "probe_dep"
description = "An invented probe package"

[pipe.entry]
type        = "PipeSequence"
description = "Run the dependency's own helper"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "helper", result = "helped" }]

[pipe.helper]
type        = "PipeLLM"
description = "DEPENDENCY helper"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "DEPENDENCY helper: $data"

[pipe.orphan]
type        = "PipeLLM"
description = "A private pipe nothing reaches"
inputs      = { data = "Text" }
output      = "Text"
model       = "no_such_model_anywhere"
prompt      = "Orphan: $data"
"""

    #: The same package with `entry` naming its helper through the package's own alias and no domain, `alias->helper`.
    DEP_BUNDLE_CALLING_ITS_HELPER_BY_ALIAS: ClassVar[str] = DEP_BUNDLE.replace(
        'steps       = [{ pipe = "helper", result = "helped" }]',
        f'steps       = [{{ pipe = "{DEP_ALIAS}->helper", result = "helped" }}]',
    )

    #: The same package with `helper` a PipeFunc naming a function no registry holds, so it fails to build.
    DEP_BUNDLE_WITH_AN_UNBUILDABLE_HELPER: ClassVar[str] = DEP_BUNDLE.replace(
        'type        = "PipeLLM"\ndescription = "DEPENDENCY helper"\ninputs      = { data = "Text" }\n'
        'output      = "Text"\nprompt      = "DEPENDENCY helper: $data"',
        'type          = "PipeFunc"\ndescription   = "DEPENDENCY helper"\ninputs        = { data = "Text" }\n'
        'output        = "Text"\nfunction_name = "no_such_function_anywhere"',
    )

    #: A consumer whose sequence calls the package's entry.
    CONSUMER_BUNDLE: ClassVar[str] = """domain      = "probe_consumer"
description = "A consumer of the invented probe package"
main_pipe   = "go"

[pipe.go]
type        = "PipeSequence"
description = "Call the probe package"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "github.com/invented/probe-lib/probe->probe_dep.entry", result = "out" }]
"""

    #: A second consumer bundle declaring the dependency's `domain.code` for its own helper.
    CONSUMER_HELPER_BUNDLE: ClassVar[str] = """domain      = "probe_dep"
description = "The consumer's own pipes in a domain named like the dependency's"

[pipe.helper]
type        = "PipeLLM"
description = "CONSUMER helper"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "CONSUMER helper: $data"
"""

    #: A consumer pipe of the dependency's own `domain.code`, `probe_dep.entry`, wrapping the dependency's entry.
    CONSUMER_ENTRY_WRAPPING_THE_DEPENDENCY_BUNDLE: ClassVar[str] = """domain      = "probe_dep"
description = "The consumer's own entry, in a domain named like the dependency's"

[pipe.entry]
type        = "PipeSequence"
description = "Wrap the dependency's entry of the same domain and code"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "github.com/invented/probe-lib/probe->probe_dep.entry", result = "out" }]
"""

    @classmethod
    def consumer_calling(cls, *, pipe_ref: str) -> str:
        """A consumer whose single step names `pipe_ref`."""
        return f"""domain      = "probe_consumer"
description = "A consumer naming one pipe of the probe package"

[pipe.go]
type        = "PipeSequence"
description = "Call one pipe"
inputs      = {{ data = "Text" }}
output      = "Text"
steps       = [{{ pipe = "{pipe_ref}", result = "out" }}]
"""


class TwoPackagesSharingADomainTestData:
    """Two installed packages that both declare `shared.entry` calling `shared.helper`; nothing here is real."""

    PACKAGES: ClassVar[dict[str, str]] = {"left": "github.com/invented/left-lib/left", "right": "github.com/invented/right-lib/right"}

    @classmethod
    def manifest(cls, *, name: str) -> str:
        return f"""[package]
name        = "{name}"
address     = "github.com/invented/{name}-lib"
version     = "1.0.0"
description = "An invented package named {name}"
"""

    @classmethod
    def bundle(cls, *, name: str) -> str:
        return f"""domain      = "shared"
description = "The {name} package's shared domain"

[pipe.entry]
type        = "PipeSequence"
description = "Run the {name} package's helper"
inputs      = {{ data = "Text" }}
output      = "Text"
steps       = [{{ pipe = "helper", result = "helped" }}]

[pipe.helper]
type        = "PipeLLM"
description = "{name.upper()} helper"
inputs      = {{ data = "Text" }}
output      = "Text"
prompt      = "{name} helper: $data"
"""

    CONSUMER_BUNDLE: ClassVar[str] = """domain      = "two_consumer"
description = "A consumer of both invented packages"

[pipe.go]
type        = "PipeSequence"
description = "Call both packages"
inputs      = { data = "Text" }
output      = "Text"
steps       = [
  { pipe = "github.com/invented/left-lib/left->shared.entry", result = "from_left" },
  { pipe = "github.com/invented/right-lib/right->shared.entry", result = "out" },
]
"""


class TwoDomainPackageTestData:
    """An installed package with two domains declaring the same pipe code, exporting only one of them; nothing here is real."""

    METHOD_NAME: ClassVar[str] = "twodom"
    DEP_ALIAS: ClassVar[str] = "github.com/invented/twodom-lib/twodom"

    MANIFEST: ClassVar[str] = """[package]
name        = "twodom"
address     = "github.com/invented/twodom-lib"
version     = "1.0.0"
description = "An invented two-domain package"

[exports.dom_a]
pipes = ["x"]
"""

    BUNDLE_A: ClassVar[str] = """domain      = "dom_a"
description = "The exported domain"

[pipe.x]
type        = "PipeSequence"
description = "Call the other domain's x"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "dom_b.x", result = "out" }]
"""

    BUNDLE_B: ClassVar[str] = """domain      = "dom_b"
description = "The private domain"

[pipe.x]
type        = "PipeLLM"
description = "The private domain's x"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "x: $data"
"""


class FailedExportWithAPrivateNamesakeTestData:
    """A probe package whose exported `dom_a.x` fails to build while a private `dom_b.x` of the same code loads; nothing here is real.

    `dom_a.entry` names `x` through the package's own alias and no domain, and `dom_a.other` reaches the private `dom_b.x`.
    """

    MANIFEST: ClassVar[str] = """[package]
name        = "probe"
address     = "github.com/invented/probe-lib"
version     = "1.0.0"
description = "An invented probe package"

[exports.dom_a]
pipes = ["x", "entry", "other"]
"""

    BUNDLE_A: ClassVar[str] = """domain      = "dom_a"
description = "The exported domain"

[pipe.x]
type          = "PipeFunc"
description   = "The exported x, which fails to build"
inputs        = { data = "Text" }
output        = "Text"
function_name = "no_such_function_anywhere"

[pipe.entry]
type        = "PipeSequence"
description = "Call x by the package's alias and its bare code"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "github.com/invented/probe-lib/probe->x", result = "out" }]

[pipe.other]
type        = "PipeSequence"
description = "Reach the private domain's x"
inputs      = { data = "Text" }
output      = "Text"
steps       = [{ pipe = "dom_b.x", result = "out" }]
"""

    BUNDLE_B: ClassVar[str] = """domain      = "dom_b"
description = "The private domain"

[pipe.x]
type        = "PipeLLM"
description = "The private x"
inputs      = { data = "Text" }
output      = "Text"
prompt      = "private x: $data"
"""
