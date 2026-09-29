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

    #: The consumer's `Digest` has a field typed by the dependency's `Note`. Its sequence steps into the dependency's
    #: pipe, which is what makes the loader discover the package: a concept ref alone does not (L-260929-9c8eac).
    CONSUMER_BUNDLE: ClassVar[str] = """domain      = "invented_consumer"
description = "A consumer of the invented notes library"

[concept.Digest]
description = "A digest built around one note"

[concept.Digest.structure]
note    = { type = "concept", concept_ref = "github.com/invented/notes-lib/notes->invented_notes.Note", description = "The note", required = true }
summary = { type = "text", description = "What the note says", required = true }

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
