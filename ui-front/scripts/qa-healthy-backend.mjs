const frontendBase = (process.env.UI_FRONT_BASE ?? "http://127.0.0.1:3000").replace(/\/$/, "");
const apiBase = (process.env.UI_API_BASE ?? process.env.NEXT_PUBLIC_UI_API_BASE ?? "http://127.0.0.1:8010/api").replace(/\/$/, "");

const failures = [];

function pass(label, detail) {
  console.log(`OK   ${label}${detail ? ` — ${detail}` : ""}`);
}

function fail(label, detail) {
  failures.push({ label, detail });
  console.error(`FAIL ${label}${detail ? ` — ${detail}` : ""}`);
}

function expect(condition, label, detail) {
  if (condition) {
    pass(label, detail);
  } else {
    fail(label, detail);
  }
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json, text/html;q=0.9,*/*;q=0.8",
    },
  });
  const text = await response.text();
  return { response, text };
}

async function checkApiJson(path, label, validator) {
  const url = `${apiBase}${path}`;
  try {
    const { response, text } = await fetchText(url);

    expect(response.ok, `${label} status`, `${response.status} ${response.statusText}`);
    if (!response.ok) {
      return null;
    }

    let payload;
    try {
      payload = text ? JSON.parse(text) : null;
      pass(`${label} json`, "Payload parsed successfully");
    } catch (error) {
      fail(`${label} json`, error instanceof Error ? error.message : String(error));
      return null;
    }

    try {
      validator(payload);
    } catch (error) {
      fail(`${label} shape`, error instanceof Error ? error.message : String(error));
      return payload;
    }

    pass(`${label} shape`, "Expected fields present");
    return payload;
  } catch (error) {
    fail(label, error instanceof Error ? error.message : String(error));
    return null;
  }
}

async function checkFrontendRoute(path) {
  const url = `${frontendBase}${path}`;
  try {
    const { response, text } = await fetchText(url);
    expect(response.ok, `route ${path} status`, `${response.status} ${response.statusText}`);
    if (!response.ok) {
      return;
    }

    const contentType = response.headers.get("content-type") ?? "";
    expect(contentType.includes("text/html"), `route ${path} content-type`, contentType || "missing content-type");
    expect(text.includes("<html"), `route ${path} html shell`, "Response contains HTML document markup");
    expect(text.includes("/_next/") || text.includes("__NEXT_DATA__"), `route ${path} next payload`, "Response includes Next.js assets");
  } catch (error) {
    fail(`route ${path}`, error instanceof Error ? error.message : String(error));
  }
}

function requireObject(payload, keys, label) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${label} must be an object`);
  }

  for (const key of keys) {
    if (!(key in payload)) {
      throw new Error(`${label} missing key: ${key}`);
    }
  }
}

console.log(`Healthy-backend QA`);
console.log(`- UI API:   ${apiBase}`);
console.log(`- Frontend: ${frontendBase}`);

await checkApiJson("/health", "api health", (payload) => {
  requireObject(payload, ["status"], "health payload");
  if (payload.status !== "ok") {
    throw new Error(`unexpected health status: ${String(payload.status)}`);
  }
});

const overview = await checkApiJson("/overview", "overview endpoint", (payload) => {
  requireObject(payload, ["generated_at", "manifest_entry_count", "strategy_index_entry_count", "live_slots"], "overview payload");
  if (!Array.isArray(payload.live_slots)) {
    throw new Error("overview live_slots must be an array");
  }
});

await checkApiJson("/execution/summary", "execution summary endpoint", (payload) => {
  requireObject(payload, ["generated_at", "live_state", "open_trades", "unmatched_closed_deals", "recent_trade_log"], "execution summary payload");
  if (!Array.isArray(payload.recent_trade_log)) {
    throw new Error("execution recent_trade_log must be an array");
  }
});

await checkApiJson("/pool/summary", "pool summary endpoint", (payload) => {
  requireObject(payload, ["generated_at", "total", "status_counts", "by_slot", "top_strategies"], "pool summary payload");
  if (!Array.isArray(payload.by_slot) || !Array.isArray(payload.top_strategies)) {
    throw new Error("pool summary slot and strategy collections must be arrays");
  }
});

await checkApiJson("/manifest", "manifest endpoint", (payload) => {
  requireObject(payload, ["source", "entry_count", "entries"], "manifest payload");
  if (!Array.isArray(payload.entries)) {
    throw new Error("manifest entries must be an array");
  }
});

const strategies = await checkApiJson("/strategies", "strategies endpoint", (payload) => {
  if (!Array.isArray(payload)) {
    throw new Error("strategies payload must be an array");
  }
});

if (Array.isArray(strategies) && strategies.length && strategies[0]?.name) {
  await checkApiJson(`/strategies/${encodeURIComponent(strategies[0].name)}`, "strategy detail endpoint", (payload) => {
    requireObject(payload, ["name"], "strategy detail payload");
  });
} else {
  pass("strategy detail endpoint", "Skipped direct detail probe because the strategies list is empty");
}

await checkApiJson("/audit/timeline?limit=25", "audit timeline endpoint", (payload) => {
  requireObject(payload, ["generated_at", "events"], "audit timeline payload");
  if (!Array.isArray(payload.events)) {
    throw new Error("audit timeline events must be an array");
  }
});

if (overview) {
  pass(
    "overview summary",
    `${overview.manifest_entry_count} manifest entries · ${overview.strategy_index_entry_count} indexed strategies`,
  );
}

for (const path of ["/", "/execution", "/pool", "/manifest", "/audit"]) {
  await checkFrontendRoute(path);
}

if (failures.length) {
  console.error(`\nHealthy-backend QA failed with ${failures.length} issue(s).`);
  for (const failure of failures) {
    console.error(`- ${failure.label}${failure.detail ? `: ${failure.detail}` : ""}`);
  }
  process.exitCode = 1;
} else {
  console.log("\nHealthy-backend QA passed. Backend payloads and primary frontend routes are reachable.");
}
