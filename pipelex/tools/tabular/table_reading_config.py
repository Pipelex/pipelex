from typing import Annotated

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class TableReadingConfig(ConfigModel):
    """`[runtime.table_reading]`: how large a spreadsheet the runtime reads into records.

    Whoever supplies the file chooses its size, and an Excel workbook is a ZIP archive whose few compressed kilobytes can
    declare millions of cells, so both bounds are checked before the cells are read, or, for a CSV file, while it is
    parsed, and a file past either is refused as ``input.too_large``:

    - ``max_workbook_uncompressed_bytes`` is the most bytes the parts of an Excel workbook (`.xlsx`) may hold once
      decompressed, summed from the sizes its archive declares before anything is decompressed. The workbook is loaded
      whole into memory, so this bounds the memory a load takes.
    - ``max_table_cells`` is the most cells, rows times columns, the table read may span. In a workbook, every row the
      Table declares counts, since each is a data row the read makes a record of, even past the sheet's last filled row;
      only the columns are clipped to the sheet's extent, and a Table counts at least one column wide. In a CSV file,
      the header's cells and each data line's count, a line narrower than the header counting as wide as it.
    """

    max_workbook_uncompressed_bytes: Annotated[int, Field(ge=1)]
    max_table_cells: Annotated[int, Field(ge=1)]
