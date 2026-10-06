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


class LedgerPackageTestData:
    """An installed method package whose sequence binds fields of its own `Invoice`, and consumers binding the same; nothing here is real.

    A package's concept reaches a consumer's sequence as the output of one of the package's pipes, or as a field the consumer types
    with the package's alias. Its concepts are held in the consumer's library only under that alias, so a binding walking them must
    read them there, and never a consumer concept spelled the same.
    """

    METHOD_NAME: ClassVar[str] = "ledger"
    DEP_ALIAS: ClassVar[str] = "github.com/invented/ledger-lib/ledger"

    DEP_MANIFEST: ClassVar[str] = """[package]
name        = "ledger"
address     = "github.com/invented/ledger-lib"
version     = "1.0.0"
description = "An invented ledger package"

[exports.invented_ledger]
pipes = ["make_invoice", "read_invoice", "write_line"]
"""

    DEP_BUNDLE: ClassVar[str] = """domain      = "invented_ledger"
description = "An invented ledger package"

[concept.Supplier]
description = "Who sent an invoice"

[concept.Supplier.structure]
name = { type = "text", description = "The supplier's name", required = true }

[concept.Invoice]
description = "An invoice kept in the ledger"

[concept.Invoice.structure]
total    = { type = "number", description = "The amount due, in euros", required = true }
supplier = { type = "concept", concept_ref = "Supplier", description = "Who sent it", required = true }

[pipe.make_invoice]
type        = "PipeCompose"
description = "Writes out an invoice for an amount and a supplier"
inputs      = { amount = "Number", sender = "Text" }
output      = "Invoice"

[pipe.make_invoice.construct]
total    = { from = "amount.number" }
supplier = { name = { from = "sender.text" } }

[pipe.write_line]
type        = "PipeCompose"
description = "Writes the ledger line of a supplier and an amount"
inputs      = { supplier_name = "Text", total_amount = "Number" }
output      = "Text"
template    = "$supplier_name: $total_amount euros"

[pipe.read_invoice]
type        = "PipeSequence"
description = "Binds the supplier's name and the total of an invoice, then writes its ledger line"
inputs      = { invoice = "Invoice" }
output      = "Text"
steps       = [
  { from = "invoice.supplier.name", result = "supplier_name" },
  { from = "invoice.total", result = "total_amount" },
  { pipe = "write_line", result = "line" },
]
"""

    #: The consumer binds the fields of an invoice the package makes, and has the package read one with its own bindings.
    CONSUMER_BUNDLE: ClassVar[str] = """domain      = "invented_books"
description = "A consumer of the invented ledger package"

[pipe.check_invoice]
type        = "PipeSequence"
description = "Has the package make an invoice, binds its fields, then writes the package's ledger line"
inputs      = { amount = "Number", sender = "Text" }
output      = "Text"
steps       = [
  { pipe = "github.com/invented/ledger-lib/ledger->invented_ledger.make_invoice", result = "invoice" },
  { from = "invoice.supplier.name", result = "supplier_name" },
  { from = "invoice.total", result = "total_amount" },
  { pipe = "github.com/invented/ledger-lib/ledger->invented_ledger.write_line", result = "line" },
]

[pipe.relay_invoice]
type        = "PipeSequence"
description = "Has the package make an invoice and read it with its own bindings"
inputs      = { amount = "Number", sender = "Text" }
output      = "Text"
steps       = [
  { pipe = "github.com/invented/ledger-lib/ledger->invented_ledger.make_invoice", result = "invoice" },
  { pipe = "github.com/invented/ledger-lib/ledger->invented_ledger.read_invoice", result = "line" },
]
"""

    #: A consumer bundle declaring `invented_ledger.Invoice` and `invented_ledger.Supplier` of its own, with other fields, and a
    #: concept of its own whose field the consumer types with the package's `Invoice`.
    CONSUMER_NAMESAKE_BUNDLE: ClassVar[str] = """domain      = "invented_ledger"
description = "The consumer's own concepts, in a domain named like the package's"

[concept.Supplier]
description = "The consumer's own idea of a supplier"

[concept.Supplier.structure]
city = { type = "text", description = "Where the supplier is", required = true }

[concept.Invoice]
description = "The consumer's own idea of an invoice"

[concept.Invoice.structure]
amount   = { type = "number", description = "The amount, in the consumer's words", required = true }
supplier = { type = "concept", concept_ref = "Supplier", description = "Who sent it", required = true }

[concept.Filing]
description = "The consumer's filing of an invoice the package keeps"

[concept.Filing.structure.invoice]
type        = "concept"
concept_ref = "github.com/invented/ledger-lib/ledger->invented_ledger.Invoice"
description = "The invoice filed"
required    = true

[pipe.read_own_invoice]
type        = "PipeSequence"
description = "Binds the fields of the consumer's own invoice"
inputs      = { invoice = "Invoice" }
output      = "Text"
steps       = [
  { from = "invoice.amount", result = "amount" },
  { from = "invoice.supplier.city", result = "city" },
]

[pipe.read_filing]
type        = "PipeSequence"
description = "Binds the supplier's name off the package's invoice a filing holds"
inputs      = { filing = "Filing" }
output      = "Text"
steps       = [
  { from = "filing.invoice.supplier.name", result = "supplier_name" },
]
"""
