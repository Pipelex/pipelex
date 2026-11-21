from typing import Any

from pydantic import BaseModel, create_model

from pipelex.core.concepts.concept import Concept
from pipelex.libraries.crate_class_cache import CrateClassCache, CrateClasses


def _built(*, class_names: list[str]) -> CrateClasses:
    """What a load of a crate holding one structured concept per name would have built."""
    concepts = [
        Concept(domain_code="cached", code=class_name, description=f"the {class_name}", structure_class_name=f"cached__{class_name}")
        for class_name in class_names
    ]
    classes: dict[str, type[Any]] = {f"cached__{class_name}": create_model(f"cached__{class_name}", title=(str, ...)) for class_name in class_names}
    return CrateClasses(concepts=concepts, classes=classes)


SEED: dict[str, type[Any]] = {"BaseModel": BaseModel}


class TestCrateClassCache:
    def test_hit_returns_the_same_classes_and_copied_concepts(self):
        """A lookup under the same seed hands back the very class objects kept, and concepts a library may change freely."""
        cache = CrateClassCache()
        built = _built(class_names=["Idea", "Verdict"])
        cache.insert(fingerprint="crate-a", seed=SEED, built=built, max_classes=10)

        first_hit = cache.lookup(fingerprint="crate-a", seed=dict(SEED))
        second_hit = cache.lookup(fingerprint="crate-a", seed=SEED)
        assert first_hit is not None
        assert second_hit is not None
        assert first_hit.classes == built.classes
        for class_name, structure_class in built.classes.items():
            assert first_hit.classes[class_name] is structure_class
            assert second_hit.classes[class_name] is structure_class
        assert [concept.concept_ref for concept in first_hit.concepts] == ["cached.Idea", "cached.Verdict"]
        assert all(hit_concept is not kept for hit_concept, kept in zip(first_hit.concepts, built.concepts, strict=True))
        first_hit.concepts[0].description = "changed by a run"
        third_hit = cache.lookup(fingerprint="crate-a", seed=SEED)
        assert third_hit is not None
        assert third_hit.concepts[0].description == "the Idea"

    def test_misses_on_another_crate_or_another_seed(self):
        """A crate kept under one starting registry is not served to a load starting from another, nor to another crate."""
        cache = CrateClassCache()
        cache.insert(fingerprint="crate-a", seed=SEED, built=_built(class_names=["Idea"]), max_classes=10)

        assert cache.lookup(fingerprint="crate-b", seed=SEED) is None
        other_seed: dict[str, type[Any]] = {"BaseModel": create_model("BaseModel")}
        assert cache.lookup(fingerprint="crate-a", seed=other_seed) is None
        assert cache.lookup(fingerprint="crate-a", seed={**SEED, "Extra": BaseModel}) is None

    def test_first_insert_is_kept(self):
        """Two loads that missed together both insert, and every later load gets the first one's classes."""
        cache = CrateClassCache()
        first = _built(class_names=["Idea"])
        second = _built(class_names=["Idea"])
        cache.insert(fingerprint="crate-a", seed=SEED, built=first, max_classes=10)
        cache.insert(fingerprint="crate-a", seed=SEED, built=second, max_classes=10)

        hit = cache.lookup(fingerprint="crate-a", seed=SEED)
        assert hit is not None
        assert hit.classes["cached__Idea"] is first.classes["cached__Idea"]
        assert hit.classes["cached__Idea"] is not second.classes["cached__Idea"]

    def test_a_new_seed_replaces_the_entry(self):
        """When the starting registry changed, the crate's newer classes replace the ones built under the old registry."""
        cache = CrateClassCache()
        newer_seed: dict[str, type[Any]] = {**SEED, "Extra": BaseModel}
        cache.insert(fingerprint="crate-a", seed=SEED, built=_built(class_names=["Idea"]), max_classes=10)
        newer = _built(class_names=["Idea"])
        cache.insert(fingerprint="crate-a", seed=newer_seed, built=newer, max_classes=10)

        assert cache.lookup(fingerprint="crate-a", seed=SEED) is None
        hit = cache.lookup(fingerprint="crate-a", seed=newer_seed)
        assert hit is not None
        assert hit.classes["cached__Idea"] is newer.classes["cached__Idea"]
        assert cache.fingerprints() == ["crate-a"]

    def test_bound_evicts_the_least_recently_used_crate(self):
        """The classes kept over all crates stay within the bound, the crate used longest ago leaving first."""
        cache = CrateClassCache()
        cache.insert(fingerprint="crate-a", seed=SEED, built=_built(class_names=["One", "Two"]), max_classes=5)
        cache.insert(fingerprint="crate-b", seed=SEED, built=_built(class_names=["One", "Two"]), max_classes=5)
        assert cache.lookup(fingerprint="crate-a", seed=SEED) is not None

        cache.insert(fingerprint="crate-c", seed=SEED, built=_built(class_names=["One", "Two"]), max_classes=5)
        assert cache.fingerprints() == ["crate-a", "crate-c"]
        assert cache.lookup(fingerprint="crate-b", seed=SEED) is None

        cache.insert(fingerprint="crate-d", seed=SEED, built=_built(class_names=["One", "Two", "Three", "Four", "Five", "Six"]), max_classes=5)
        assert cache.fingerprints() == ["crate-a", "crate-c"]

    def test_zero_bound_keeps_nothing(self):
        cache = CrateClassCache()
        cache.insert(fingerprint="crate-a", seed=SEED, built=_built(class_names=["Idea"]), max_classes=0)
        cache.insert(fingerprint="crate-b", seed=SEED, built=_built(class_names=[]), max_classes=0)
        assert cache.fingerprints() == []

    def test_incomplete_class_is_not_kept(self):
        """A class whose forward reference is unresolved would be rebuilt by the next load, so its crate is not kept."""
        cache = CrateClassCache()
        built = _built(class_names=["Idea"])
        incomplete = create_model("cached__Holder", item=("cached__Missing", ...))
        assert not incomplete.__pydantic_complete__
        built.classes["cached__Holder"] = incomplete
        cache.insert(fingerprint="crate-a", seed=SEED, built=built, max_classes=10)
        assert cache.lookup(fingerprint="crate-a", seed=SEED) is None

    def test_clear_forgets_every_crate(self):
        cache = CrateClassCache()
        cache.insert(fingerprint="crate-a", seed=SEED, built=_built(class_names=["Idea"]), max_classes=10)
        cache.clear()
        assert cache.lookup(fingerprint="crate-a", seed=SEED) is None
        assert cache.fingerprints() == []
