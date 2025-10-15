from pipelex.libraries.library_manager import LibraryManager


class LibraryManagerFactory:
    @classmethod
    def make_empty(cls) -> LibraryManager:
        return LibraryManager()
