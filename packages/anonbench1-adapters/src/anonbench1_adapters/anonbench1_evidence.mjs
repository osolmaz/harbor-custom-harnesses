// Selective evidence in the existing Pi session, never raw payloads or headers.
const TYPE = "anonbench1-provider-evidence";
const TOKEN_FIELDS = [
  "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "total_tokens",
  "cache_read_input_tokens", "cache_creation_input_tokens",
];

export default function campaignEvidence(pi) {
  let evidence;
  function retain(list, value) {
    if (list.some((entry) => JSON.stringify(entry) === JSON.stringify(value))) return;
    if (list.length < 64) list.push(value);
    else evidence.truncated = true;
  }
  pi.on("turn_start", () => {
    evidence = {
      schema_version: 1,
      codemode_active: pi.getActiveTools().includes("codemode"),
      models: [], usage: [], truncated: false,
    };
  });
  pi.on("provider_stream_event", (event) => {
    if (!evidence) return;
    const raw = event.data;
    if (!raw || typeof raw !== "object") return;
    for (const chunk of [raw, raw.response, raw.message]) {
      if (!chunk || typeof chunk !== "object") continue;
      // The outer event.model is requested metadata, not provider evidence.
      if (typeof chunk.model === "string" && chunk.model.length > 0) {
        if (chunk.model.length <= 512) {
          retain(evidence.models, { requested_model: event.model, observed_model: chunk.model });
        } else evidence.truncated = true;
      }
      if (chunk.usage && typeof chunk.usage === "object") {
        const counts = Object.fromEntries(TOKEN_FIELDS.flatMap((key) => {
          const value = chunk.usage[key];
          return Number.isFinite(value) && value >= 0 ? [[key, value]] : [];
        }));
        if (Object.keys(counts).length) retain(evidence.usage, counts);
      }
    }
  });
  function finish(messageEntryId) {
    if (!evidence) return;
    pi.appendEntry(TYPE, {
      ...evidence,
      message_entry_id: messageEntryId ?? null,
      scope: "turn observations; nested calls and aggregate completeness are not qualified",
    });
    evidence = undefined;
  }
  pi.on("turn_end", (event) => finish(event.messageEntryId));
  pi.on("agent_end", () => finish(null));
}
