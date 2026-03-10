export const healthFixture = {
  status: "ok",
};

export const ingestResultFixture = {
  doc_id: "doc_dashboard_ingest",
  doc_version_id: "dv_dashboard_ingest",
  chunk_ids: ["chunk_dashboard_ingest"],
  jobs: [],
  source_path: "next_console.md",
};

export const traceSummariesFixture = [
  {
    trace_id: "trace_dash_001",
    domain: "BJJ",
    task: "coach",
    gate_label: "HIGH_EVIDENCE",
    validator_pass: true,
  },
  {
    trace_id: "trace_dash_002",
    domain: "NOTES",
    task: "literary",
    gate_label: "n/a",
    validator_pass: null,
  },
];

export const traceDetailFixture = {
  trace_id: "trace_dash_001",
  runtime_config_snapshot: {
    embedding_version_id: "mock-embedding-v1",
    prompt_versions: {
      bjj_coach: "bjj.v1",
      literary: "literary.v1",
      safe_summary: "safe-summary.v1",
      replan: "replan.v1",
    },
    policy_version: "BASE",
    trace_capture_level: "minimal",
    retrieval: {},
    orchestrator: {},
    bjj_gate: {},
    model_routing: {
      profile_name: "fake",
      provider: "mock",
      base_model: "mock-bjj-base",
      policy_model: "policy://pending",
      embedding_model: "mock-embedding-model",
    },
    generation: {},
  },
  request_log: {
    entrypoint: "chat",
    task: "coach",
    domain: "BJJ",
  },
  retrieval_log: {
    probe_stats: {
      k: 3,
    },
  },
  evidence_log: {
    items: [
      {
        evidence_id: "ev_001",
      },
    ],
  },
  generation_log: {
    model: "mock-bjj-base",
    prompt_version: "bjj.v1",
  },
};

export const replayResultFixture = {
  trace_id: "trace_dash_001",
  final_answer: {
    answer_type: "FULL",
    summary: "Keep your elbow inside before standing up.",
  },
};

export const chatTurnFixture = {
  response_type: "clarify_request",
  conversation_id: "conv_fixture_001",
  trace_id: "trace_chat_001",
  response: {
    who: "orchestrator",
    slot: "orientation",
    options: ["上位", "下位"],
    template_id: "ASK_ORIENTATION_V1",
    round: 1,
    why: "需要先确定方位。",
  },
};

export const evalRunsFixture = [
  {
    eval_run_id: "eval_existing_001",
    eval_set_id: "manual_eval",
    model_variant: "base",
    run_status: "completed",
    golden_case_count: 1,
  },
];

export const evalLaunchFixture = {
  eval_run_id: "eval_launch_002",
};

export const refreshedEvalRunsFixture = [
  ...evalRunsFixture,
  {
    eval_run_id: "eval_launch_002",
    eval_set_id: "manual_eval",
    model_variant: "base",
    run_status: "completed",
    golden_case_count: 1,
  },
];
