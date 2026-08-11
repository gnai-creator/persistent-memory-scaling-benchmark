"""Thin adapter over the public TrustGraph Python API."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any


class TrustGraphDependencyError(RuntimeError):
    pass


def _sdk() -> tuple[Any, Any, Any, Any]:
    try:
        from trustgraph.api import Api, Triple
        from trustgraph.knowledge import Literal, Uri
    except ImportError as exc:
        raise TrustGraphDependencyError(
            "TrustGraph client dependency is unavailable: "
            f"{exc}. Install with: pip install -e '.[trustgraph]'"
        ) from exc
    return Api, Triple, Uri, Literal


class TrustGraphClient:
    def __init__(
        self,
        url: str,
        token: str,
        workspace: str = "default",
        flow_id: str = "default",
        collection: str = "default",
        timeout: int = 600,
    ) -> None:
        Api, _, _, _ = _sdk()
        self.api = Api(url=url, token=token, workspace=workspace, timeout=timeout)
        self.flow_id = flow_id
        self.collection = collection

    def list_flows(self) -> list[str]:
        return list(self.api.flow().list())

    def start_flow(self, model: str, embeddings_model: str) -> None:
        flows = self.list_flows()
        if self.flow_id in flows:
            return
        self.api.flow().start(
            blueprint_name="everything",
            id=self.flow_id,
            description="PMSB TG-0 smoke",
            parameters={
                "llm-model": model,
                "llm-rag-model": model,
                "embeddings-model": embeddings_model,
                "reranker-model": "ms-marco-MiniLM-L-12-v2",
                "chunk-size": "2000",
                "chunk-overlap": "50",
                "llm-temperature": "0",
            },
        )

    def import_events(self, events: Iterable[dict[str, Any]]) -> int:
        return self.import_structured_events(events, document_id="pmsb-tg0", include_contexts=True)

    def import_structured_events(self, events: Iterable[dict[str, Any]], document_id: str,
                                 include_contexts: bool = False) -> int:
        _, Triple, _, _ = _sdk()
        event_list = list(events)

        def triples():
            for event in event_list:
                for item in event["triples"]:
                    yield Triple(
                        s=item["s"],
                        p=item["p"],
                        o=item["o"],
                        o_datatype="" if item["object_type"] == "iri" else "http://www.w3.org/2001/XMLSchema#string",
                        o_language="" if item["object_type"] == "iri" else event["language"],
                    )

        self.api.bulk().import_triples(
            flow=self.flow_id,
            triples=triples(),
            metadata={"id": document_id, "metadata": [], "collection": self.collection},
        )

        def contexts():
            for event in event_list:
                for item in event["entity_contexts"]:
                    yield {"entity": {"t": "i", "i": item["entity"]}, "context": item["context"]}

        if include_contexts:
            self.api.bulk().import_entity_contexts(
                flow=self.flow_id,
                contexts=contexts(),
                metadata={"id": document_id, "metadata": [], "collection": self.collection},
            )
        return sum(len(event["triples"]) for event in event_list)

    def export_triples(self) -> Iterable[Any]:
        return self.api.bulk().export_triples(flow=self.flow_id)

    def query_subject(self, subject: str, limit: int = 20) -> list[Any]:
        _, _, Uri, _ = _sdk()
        return list(
            self.api.flow().id(self.flow_id).triples_query(
                s=Uri(subject), collection=self.collection, limit=limit
            )
        )

    def wait_for_subject(self, subject: str, minimum: int, timeout: float = 180.0) -> list[Any]:
        deadline = time.monotonic() + timeout
        last: list[Any] = []
        while time.monotonic() < deadline:
            last = self.query_subject(subject)
            if len(last) >= minimum:
                return last
            time.sleep(2)
        raise TimeoutError(f"subject {subject!r} returned {len(last)} triples; expected {minimum}")

    def graph_rag(self, question: str) -> Any:
        return self.api.flow().id(self.flow_id).graph_rag(
            query=question,
            collection=self.collection,
            entity_limit=20,
            triple_limit=20,
            max_subgraph_size=100,
            max_path_length=2,
            edge_score_limit=20,
            edge_limit=10,
            max_reranker_input=100,
        )

    def document_rag(self, question: str) -> Any:
        return self.api.flow().id(self.flow_id).document_rag(
            query=question, collection=self.collection, doc_limit=5, fetch_limit=15
        )

    def load_text(self, text: str, document_id: str) -> Any:
        # Use the public librarian workflow.  The generated 2.8.12 gateway
        # contains a text-load dispatcher, but its capability registry omits
        # that route and therefore returns HTTP 404.
        library = self.api.library()
        added = library.add_document(
            document=text.encode("utf-8"),
            id=document_id,
            metadata=[],
            title="PMSB TG-0 synthetic events",
            comments="Frozen 100-event TG-0 smoke workload",
            kind="text/plain",
            tags=["pmsb", "tg0"],
        )
        library.start_processing(
            id=f"processing-{document_id}",
            document_id=document_id,
            flow=self.flow_id,
            collection=self.collection,
            tags=["pmsb", "tg0"],
        )
        return added

    def wait_for_document_rag(
        self, question: str, timeout: float = 300.0
    ) -> Any:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = self.document_rag(question)
                text = getattr(result, "text", str(result))
                if text.strip():
                    return result
            except Exception as exc:  # the document pipeline is asynchronous
                last_error = exc
            time.sleep(5)
        detail = f": {last_error}" if last_error else ""
        raise TimeoutError(f"DocumentRAG did not become ready within {timeout}s{detail}")
