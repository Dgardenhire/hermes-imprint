"""Claude's strict output mode refuses the format request itself (HTTP 400). Letterpress then asks in plain words and reads
the JSON from the reply, the way a plain prompt does, so it works on any model."""
import asyncio
import unittest

from _load import runtime, Result

REFUSAL = RuntimeError("Incomplete upstream response (first upstream attempt: status 400, upstream said: "
                       "output_config.format.schema: For 'object' type, 'additionalProperties' must be explicitly set to false)")


HERMES_NO = ValueError("Only json_schema structured output is supported")


class Llm:
    def __init__(self):
        self.calls = []

    async def acomplete_structured(self, **kw):
        self.calls.append(kw)
        if kw.get("json_mode") or kw.get("json_schema") is not None:
            raise REFUSAL
        return Result(parsed=None, text='```json\n{"slides": [{"id": "s1"}]}\n```')


class HermesDeclines(Llm):
    """Hermes raises before any call when json_mode is asked of this provider."""
    async def acomplete_structured(self, **kw):
        self.calls.append(kw)
        if kw.get("json_mode"):
            raise HERMES_NO
        return Result(parsed=None, text='{"slides": [{"id": "s1"}]}')


class ClaudeFormat(unittest.TestCase):
    def test_three_calls_at_once_all_recover(self):
        class Slow(HermesDeclines):
            async def acomplete_structured(self, **kw):
                await asyncio.sleep(0.01)  # every call is in flight before any refusal comes back
                return await super().acomplete_structured(**kw)
        llm = Slow()
        m = runtime.Model(llm=llm)
        m.use_task = False

        async def three():
            return await asyncio.gather(*[m.structured(system="s", instructions="Write.", body="b", schema=None, purpose="t") for _ in range(3)])
        outs = asyncio.run(three())
        self.assertTrue(all(o == {"slides": [{"id": "s1"}]} for o in outs))

    def test_hermes_declines_json_mode_then_plain(self):
        llm = HermesDeclines()
        m = runtime.Model(llm=llm)
        m.use_task = False
        out = asyncio.run(m.structured(system="s", instructions="Write.", body="b", schema=None, purpose="t"))
        self.assertEqual(out, {"slides": [{"id": "s1"}]})
        self.assertFalse(llm.calls[-1]["json_mode"])
        self.assertTrue(m.plain)

    def run_it(self, schema):
        llm = Llm()
        m = runtime.Model(llm=llm)
        m.use_task = False
        out = asyncio.run(m.structured(system="s", instructions="Write.", body="b", schema=schema, purpose="t"))
        return llm, out

    def test_json_mode_refused_then_plain(self):
        llm, out = self.run_it(None)
        self.assertEqual(out, {"slides": [{"id": "s1"}]})
        self.assertEqual(len(llm.calls), 2)
        last = llm.calls[-1]
        self.assertFalse(last["json_mode"])
        self.assertIsNone(last["json_schema"])
        self.assertIn("JSON object", last["instructions"])

    def test_schema_refused_then_plain_carries_the_shape(self):
        schema = {"type": "object", "properties": {"slides": {"type": "array"}}}
        llm, out = self.run_it(schema)
        self.assertEqual(out["slides"][0]["id"], "s1")
        self.assertIn('"slides"', llm.calls[-1]["instructions"])

    def test_plain_stays_on_for_later_calls(self):
        llm = Llm()
        m = runtime.Model(llm=llm)
        m.use_task = False
        for _ in range(2):
            asyncio.run(m.structured(system="s", instructions="Write.", body="b", schema=None, purpose="t"))
        self.assertEqual(len(llm.calls), 3)  # one refusal, then plain every time

    def test_other_errors_still_raise(self):
        class Bad:
            async def acomplete_structured(self, **kw):
                raise RuntimeError("connection reset")
        m = runtime.Model(llm=Bad())
        m.use_task = False
        with self.assertRaises(runtime.ModelError):
            asyncio.run(m.structured(system="s", instructions="x", body="b", schema=None, purpose="t"))


if __name__ == "__main__":
    unittest.main()
