"""Extract the same document from the recorded cache and from LIVE API calls.

Uses the shipped Pipeline / RecordingClient unchanged. The live client is pointed at a throwaway
cache dir so fixtures/recorded_responses/ in the repo is never mutated.
Live attempts are repeated to characterise run-to-run variance.
"""
import json, sys, tempfile, traceback
from pathlib import Path
from anthropic.types import ToolUseBlock
from mortgage_extractor.client import RecordingClient
from mortgage_extractor.pipeline import Pipeline
from mortgage_extractor.validator import validate
from mortgage_extractor import prompts
from mortgage_extractor.tools import doc_type_extractor, flag_for_review
from mortgage_extractor.models import MortgageExtraction

doc_path = Path(sys.argv[1]); attempts = int(sys.argv[2]) if len(sys.argv) > 2 else 3
text = doc_path.read_text()

print(f"document: {doc_path.name}\nlive attempts: {attempts}\n")

p_replay = Pipeline(client=RecordingClient(mode="replay"))
ex = p_replay.run(text)
replay = {"extraction": ex.model_dump(mode="json"), "validation": validate(ex).model_dump(mode="json")}
print("=== REPLAY (recorded fixture) ===")
print(json.dumps(replay, indent=2, sort_keys=True))

for i in range(1, attempts + 1):
    tmp = Path(tempfile.mkdtemp(prefix=f"live-cache-{i}-"))
    client = RecordingClient(mode="record", cache_dir=tmp)
    pipe = Pipeline(client=client)
    print(f"\n=== LIVE ATTEMPT {i} (fresh API calls; cache -> {tmp}) ===")
    try:
        cls = pipe.classify_document(text)
        print(f"classified: {cls.document_type}")
        # Re-issue the extract call ourselves so we can inspect the RAW tool input
        # before Pydantic validation, which is where attempt-level failures surface.
        resp = client.call(
            model=pipe.model, max_tokens=pipe.max_tokens,
            system=prompts.extractor_system_prompt(cls.document_type),
            tools=[doc_type_extractor(cls.document_type), flag_for_review()],
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": text}],
        )
        blocks = [b for b in resp.content if isinstance(b, ToolUseBlock)]
        raw = blocks[0].input if blocks else None
        print(f"tool called: {blocks[0].name if blocks else '(none)'}")
        print("RAW tool input as returned by the model:")
        print(json.dumps(raw, indent=2, sort_keys=True))
        try:
            m = MortgageExtraction.model_validate(raw)
            out = {"extraction": m.model_dump(mode="json"), "validation": validate(m).model_dump(mode="json")}
            print("pydantic validation: PASSED")
            print(json.dumps(out, indent=2, sort_keys=True))
            print(f"matches replay exactly: {out == replay}")
        except Exception:
            print("pydantic validation: *** REJECTED ***")
            traceback.print_exc(limit=1)
    except Exception:
        print("attempt raised:")
        traceback.print_exc(limit=2)
