from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from broll_expression import validate_expression
from broll_retrieval import (candidate_key, candidate_text, expression_hash, keyword_matches,
                             rank_candidates, text_hash, tokenize)
from prepare_broll_embeddings import embed, prepare
from select_broll_template import collect_reference_candidates, select


def expression(motion="flip the cards", tags=None, requirements=None):
    return {"subjects": ["boards"], "element_relation": "same position",
            "main_motion": motion, "phase_order": ["front", "flip", "back"],
            "invariants": ["position fixed"], "motion_tags": tags or ["content-flip"],
            "search_queries": ["flip card content at fixed position", "rotate front to back"],
            "requirements": requirements or {}}


def candidate(name, text, *, source="fixture", tags=None, capabilities=None):
    return {"id": name, "description": text, "reference_source": source,
            "reference_path": f"/{source}/{name}.html", "motion_tags": tags or [],
            "capabilities": capabilities or {}}


def bundle(candidates, brief, vectors, query=None):
    return {"schema_version": "1.0", "model": "test-fixture-not-a-production-model",
            "query": {"expression_sha256": expression_hash(brief), "vector": query or [1, 0]},
            "candidates": {candidate_key(item): {"text_sha256": text_hash(candidate_text(item)), "vector": vector}
                           for item, vector in zip(candidates, vectors)}}


class RetrievalTests(unittest.TestCase):
    def test_stopwords_and_substrings_do_not_match(self):
        self.assertEqual(keyword_matches("with then background facet interface", ["with", "then", "back", "face"]), [])
        self.assertIn("flip", tokenize("flipped cards"))

    def test_flip_beats_galaxy_and_generic_rotation(self):
        pool = [candidate("galaxy", "Different stars with rotation in background"),
                candidate("flip", "Flip cards front to back at fixed position", tags=["content-flip"])]
        result, info = rank_candidates(pool, expression())
        self.assertEqual(result[0]["id"], "flip")
        self.assertFalse(info["semantic"]["enabled"])
        self.assertEqual(result[0]["match_basis"], "motion")

    def test_bm25_does_not_reward_repeated_description(self):
        pool = [candidate("short", "Flip card at fixed position"),
                candidate("long", "Flip card at fixed position " + "unrelated noise " * 200)]
        result, _ = rank_candidates(pool, expression())
        self.assertEqual(result[0]["id"], "short")

    def test_chinese_motion_retrieval_without_english_query(self):
        brief = expression("翻面替换文字")
        brief.update(search_queries=["木板翻面保持位置", "翻转后背面文字可读"])
        pool = [candidate("flip", "木板翻面替换文字，位置保持"), candidate("zoom", "镜头拉远展示全景")]
        result, _ = rank_candidates(pool, brief)
        self.assertEqual(result[0]["id"], "flip")

    def test_english_query_retrieves_chinese_motion_card_without_catalog(self):
        pool = [candidate("flip", "功能卡沿 Y 轴翻面，正面变背面，中心位置保持。"),
                candidate("galaxy", "Stars turning with differential rotation in background")]
        result, info = rank_candidates(pool, expression())
        self.assertEqual(result[0]["id"], "flip")
        self.assertFalse(info["semantic"]["enabled"])

    def test_source_is_not_dropped_by_global_limit(self):
        pool = [candidate(str(i), "Flip card front to back position", source="large", tags=["content-flip"]) for i in range(80)]
        pool.append(candidate("rare", "Flip a card", source="small"))
        result, _ = rank_candidates(pool, expression(), limit=10)
        self.assertEqual(len(result), 10)
        self.assertIn("small", {item["reference_source"] for item in result})

    def test_conflicting_carrier_is_not_eligible(self):
        brief = expression(requirements={"preserves_content": True})
        pool = [candidate("flip", "Flip text", tags=["content-flip"], capabilities={"preserves_content": False}),
                candidate("carrier", "Replace carrier and preserve text", capabilities={"preserves_content": True})]
        result, _ = rank_candidates(pool, brief)
        flip = next(item for item in result if item["id"] == "flip")
        self.assertFalse(flip["matched"])
        self.assertEqual(flip["constraint_fit"]["conflicts"], ["preserves_content"])

    def test_missing_capability_is_unknown_not_conflict_or_proof(self):
        result, _ = rank_candidates([candidate("flip", "Flip card")], expression(requirements={"preserves_position": True}))
        self.assertEqual(result[0]["constraint_fit"]["status"], "unknown")
        self.assertIn("invariants", result[0]["review_required"])

    def test_final_overview_distinguishes_list_from_picker(self):
        brief = expression("逐项出现", ["progressive-reveal"], {"retains_previous": True, "final_overview": True})
        pool = [candidate("picker", "逐项出现", tags=["progressive-reveal"], capabilities={"retains_previous": False, "final_overview": False}),
                candidate("list", "逐项出现并保留前项", tags=["progressive-reveal"], capabilities={"retains_previous": True, "final_overview": True})]
        result, _ = rank_candidates(pool, brief)
        self.assertEqual(result[0]["id"], "list")
        self.assertFalse(result[1]["matched"])

    def test_invalid_requirements_fail(self):
        self.assertTrue(validate_expression(expression(requirements={"looks_good": True})))
        self.assertTrue(validate_expression(expression(requirements={"retains_source": "true"})))

    def test_true_vector_can_recall_without_lexical_overlap(self):
        pool = [candidate("unrelated", "cloud landscape"), candidate("paraphrase", "side exchange")]
        brief = expression()
        result, info = rank_candidates(pool, brief, vectors=bundle(pool, brief, [[0, 1], [1, 0]]))
        self.assertEqual(result[0]["id"], "paraphrase")
        self.assertEqual(result[0]["match_basis"], "semantic")
        self.assertTrue(info["semantic"]["enabled"])
        self.assertIn("actual_preview", result[0]["review_required"])

    def test_stale_query_is_rejected(self):
        pool = [candidate("a", "Flip")]
        brief = expression()
        vectors = bundle(pool, brief, [[1, 0]])
        brief["invariants"] = ["different fixed position"]
        with self.assertRaisesRegex(ValueError, "已过期"):
            rank_candidates(pool, brief, vectors=vectors)

    def test_stale_candidate_vector_is_skipped(self):
        pool = [candidate("a", "Flip")]
        brief = expression()
        vectors = bundle(pool, brief, [[1, 0]])
        pool[0]["description"] = "Flip with changed contents"
        _, info = rank_candidates(pool, brief, vectors=vectors)
        self.assertFalse(info["semantic"]["enabled"])
        self.assertTrue(any("旧向量" in item for item in info["semantic"]["warnings"]))

    def test_invalid_vectors_are_rejected(self):
        pool = [candidate("a", "Flip")]
        brief = expression()
        for vector in ([1], [float("nan"), 0], [0, 0], [True, 0]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                rank_candidates(pool, brief, vectors=bundle(pool, brief, [vector]))

    def test_configured_missing_repo_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "不存在"):
                collect_reference_candidates(Path(directory) / "missing", "replacement")

    def test_unconfigured_repo_is_reported_not_claimed_searched(self):
        report = select({"templates": []}, "replacement", 2, 6000, "16:9", expression_brief=expression())
        self.assertTrue(any("检索未执行" in warning for warning in report["selection_warnings"]))

    def test_scanner_collects_before_query_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shots = root / "video-shotcraft/shots/replacement"
            shots.mkdir(parents=True)
            for i in range(60):
                (shots / f"{i}.md").write_text(f"---\nname: {i}\n---\nFlip card", encoding="utf-8")
            self.assertEqual(len(collect_reference_candidates(root, "replacement")), 60)


class EmbeddingCacheTests(unittest.TestCase):
    def setUp(self):
        self.brief = expression()
        item = candidate("a", "Flip card")
        self.catalog = {"schema_version": "1.0", "candidates": [
            {"retrieval_key": candidate_key(item), "retrieval_text": candidate_text(item),
             "text_sha256": text_hash(candidate_text(item))}]}

    @patch("prepare_broll_embeddings.embed", side_effect=lambda texts, **kwargs: [[1, 0] for _ in texts])
    def test_repeat_reuses_vectors_without_calling_service(self, embed):
        result = prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="fixture")
        self.assertEqual(embed.call_count, 2)
        embed.reset_mock()
        repeated = prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="fixture", cache=result)
        self.assertEqual(result, repeated)
        embed.assert_not_called()

    @patch("prepare_broll_embeddings.embed", side_effect=lambda texts, **kwargs: [[1, 0] for _ in texts])
    def test_changed_query_reuses_candidate_embeddings(self, embed):
        cache = prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="fixture")
        embed.reset_mock()
        self.brief["main_motion"] = "replace a carrier"
        prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="fixture", cache=cache)
        self.assertEqual(embed.call_count, 1)

    @patch("prepare_broll_embeddings.embed", side_effect=lambda texts, **kwargs: [[1, 0] for _ in texts])
    def test_model_change_rebuilds_all_embeddings(self, embed):
        cache = prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="fixture")
        embed.reset_mock()
        prepare(self.catalog, self.brief, api_base="http://localhost/v1", model="other", cache=cache)
        self.assertEqual(embed.call_count, 2)


class EmbeddingEndpointTests(unittest.TestCase):
    @patch("prepare_broll_embeddings.build_opener")
    def test_endpoint_response_indexes_restore_input_order(self, opener):
        opener.return_value.open.return_value = io.BytesIO(json.dumps({"data": [
            {"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]}).encode())
        result = embed(["first", "second"], api_base="http://localhost:9999/v1", model="fixture")
        self.assertEqual(result, [[1, 0], [0, 1]])
        request = opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:9999/v1/embeddings")
        self.assertEqual(json.loads(request.data)["input"], ["first", "second"])

    @patch("prepare_broll_embeddings.build_opener")
    def test_incomplete_service_response_is_rejected(self, opener):
        opener.return_value.open.return_value = io.BytesIO(json.dumps({"data": []}).encode())
        with self.assertRaisesRegex(ValueError, "条目数"):
            embed(["first"], api_base="http://localhost:9999/v1", model="fixture")

    @patch("prepare_broll_embeddings.build_opener")
    def test_remote_cleartext_and_credential_urls_are_rejected(self, opener):
        for url in ("http://remote.example/v1", "https://user:secret@example.com/v1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                embed(["text"], api_base=url, model="fixture")
        opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
