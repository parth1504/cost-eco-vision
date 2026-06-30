import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Brain,
  Activity,
  MessageSquare,
  Shield,
  Network,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Play,
  Pause,
  RotateCcw,
  Zap,
  Eye,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  Server,
  Database,
  HardDrive,
  BarChart3,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";

const API_BASE = "http://localhost:8000";

interface AgentInfo {
  agent_id: string;
  capabilities: string[];
}

interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  operation: string;
  agent: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  attributes: Record<string, unknown>;
  events: Array<{ name: string; attributes: Record<string, unknown> }>;
  status: string;
}

interface AgentMessage {
  id: string;
  from_agent: string;
  to_agent: string;
  message_type: string;
  payload: Record<string, unknown>;
  timestamp: string;
  trace_id: string;
}

interface Decision {
  agent: string;
  action: string;
  reasoning: string;
  confidence: number;
  duration_ms: number;
  timestamp: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
}

interface SessionInfo {
  session_id: string;
  trace_id: string;
  status: string;
  resource_count: number;
  message_count: number;
  decision_count: number;
  recommendation_count: number;
  started_at: string;
  completed_at: string | null;
  verification_gates: Array<{
    gate_name: string;
    result: string;
    details: string;
  }>;
}

interface AnalysisResult {
  session: SessionInfo;
  recommendations: Array<Record<string, unknown>>;
  decisions: Decision[];
  messages: AgentMessage[];
  trace: TraceSpan[];
  interaction_graph: {
    nodes: Array<{ id: string }>;
    edges: Array<{ from: string; to: string; type: string; timestamp: string }>;
  };
  verification_summary: {
    total_gates: number;
    passed: number;
    failed: number;
    needs_review: number;
  };
  evaluation: {
    total_metrics: number;
    averages: Record<string, number>;
    benchmark_pass_rate: number;
  };
}

const AGENT_COLORS: Record<string, string> = {
  orchestrator: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  ec2_specialist: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  s3_specialist: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  dynamodb_specialist: "bg-green-500/20 text-green-400 border-green-500/30",
  critique: "bg-red-500/20 text-red-400 border-red-500/30",
  correlation: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
};

const AGENT_ICONS: Record<string, typeof Brain> = {
  orchestrator: Brain,
  ec2_specialist: Server,
  s3_specialist: HardDrive,
  dynamodb_specialist: Database,
  critique: Shield,
  correlation: Network,
};

const STATUS_ICONS: Record<string, typeof CheckCircle> = {
  passed: CheckCircle,
  failed: XCircle,
  needs_review: AlertTriangle,
  skipped: Clock,
};

const STATUS_COLORS: Record<string, string> = {
  passed: "text-green-400",
  failed: "text-red-400",
  needs_review: "text-yellow-400",
  skipped: "text-gray-400",
};

function AgentBadge({ agentId }: { agentId: string }) {
  const Icon = AGENT_ICONS[agentId] || Brain;
  const colorClass = AGENT_COLORS[agentId] || "bg-gray-500/20 text-gray-400 border-gray-500/30";
  return (
    <Badge variant="outline" className={`${colorClass} border text-xs font-mono`}>
      <Icon className="w-3 h-3 mr-1" />
      {agentId}
    </Badge>
  );
}

// ─── Trace Timeline ────────────────────────────────────────────────────────

function TraceTimeline({ spans }: { spans: TraceSpan[] }) {
  if (!spans.length) return <p className="text-sm text-muted-foreground p-4">No trace data yet</p>;

  const sorted = [...spans].sort((a, b) => a.start_time - b.start_time);
  const minTime = sorted[0].start_time;
  const maxTime = Math.max(...sorted.map((s) => s.end_time || s.start_time + 0.001));
  const totalDuration = maxTime - minTime || 1;

  return (
    <div className="space-y-1 p-2">
      {sorted.map((span) => {
        const left = ((span.start_time - minTime) / totalDuration) * 100;
        const width = Math.max(2, (span.duration_ms / (totalDuration * 1000)) * 100);
        const colorClass = AGENT_COLORS[span.agent]?.split(" ")[0] || "bg-gray-500/40";

        return (
          <div key={span.span_id} className="flex items-center gap-2 text-xs group">
            <div className="w-32 truncate text-muted-foreground font-mono">{span.agent}</div>
            <div className="flex-1 h-6 bg-muted/30 rounded relative overflow-hidden">
              <motion.div
                className={`absolute h-full rounded ${colorClass.replace("/20", "/60")}`}
                initial={{ width: 0, left: `${left}%` }}
                animate={{ width: `${width}%` }}
                transition={{ duration: 0.5, ease: "easeOut" }}
              />
              <span className="absolute inset-0 flex items-center px-2 text-xs text-foreground/70 font-mono">
                {span.operation} ({span.duration_ms.toFixed(0)}ms)
              </span>
            </div>
            <Badge
              variant="outline"
              className={`text-xs ${span.status === "ok" ? "text-green-400 border-green-500/30" : "text-red-400 border-red-500/30"}`}
            >
              {span.status}
            </Badge>
          </div>
        );
      })}
    </div>
  );
}

// ─── Agent Interaction Graph ───────────────────────────────────────────────

function InteractionGraph({
  graph,
}: {
  graph: { nodes: Array<{ id: string }>; edges: Array<{ from: string; to: string; type: string }> };
}) {
  if (!graph.nodes.length)
    return <p className="text-sm text-muted-foreground p-4">No interactions recorded</p>;

  return (
    <div className="p-4 space-y-3">
      <div className="flex flex-wrap gap-3 justify-center">
        {graph.nodes.map((node) => (
          <motion.div
            key={node.id}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className={`px-4 py-2 rounded-lg border ${AGENT_COLORS[node.id] || "bg-gray-500/20 text-gray-400 border-gray-500/30"}`}
          >
            <div className="flex items-center gap-2">
              {(() => {
                const Icon = AGENT_ICONS[node.id] || Brain;
                return <Icon className="w-4 h-4" />;
              })()}
              <span className="text-sm font-mono">{node.id}</span>
            </div>
          </motion.div>
        ))}
      </div>
      <Separator />
      <div className="space-y-1">
        {graph.edges.map((edge, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className="flex items-center gap-2 text-xs text-muted-foreground font-mono"
          >
            <AgentBadge agentId={edge.from} />
            <ArrowRight className="w-3 h-3" />
            <AgentBadge agentId={edge.to} />
            <Badge variant="secondary" className="text-xs">
              {edge.type}
            </Badge>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ─── Decision Log ──────────────────────────────────────────────────────────

function DecisionLog({ decisions }: { decisions: Decision[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  };

  if (!decisions.length)
    return <p className="text-sm text-muted-foreground p-4">No decisions recorded</p>;

  return (
    <div className="space-y-2 p-2">
      {decisions.map((d, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="border border-border/50 rounded-lg overflow-hidden"
        >
          <button
            className="w-full flex items-center gap-3 p-3 hover:bg-muted/30 transition-colors text-left"
            onClick={() => toggle(i)}
          >
            {expanded.has(i) ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )}
            <AgentBadge agentId={d.agent} />
            <span className="text-sm font-medium flex-1">{d.action}</span>
            {d.confidence > 0 && (
              <Badge variant="outline" className="text-xs">
                {(d.confidence * 100).toFixed(0)}%
              </Badge>
            )}
            {d.duration_ms > 0 && (
              <span className="text-xs text-muted-foreground">{d.duration_ms.toFixed(0)}ms</span>
            )}
          </button>
          <AnimatePresence>
            {expanded.has(i) && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="border-t border-border/30 bg-muted/10 px-4 py-3 text-sm space-y-2"
              >
                <div>
                  <span className="text-muted-foreground">Reasoning: </span>
                  <span>{d.reasoning}</span>
                </div>
                {Object.keys(d.inputs).length > 0 && (
                  <div>
                    <span className="text-muted-foreground">Inputs: </span>
                    <code className="text-xs bg-muted/30 p-1 rounded">{JSON.stringify(d.inputs)}</code>
                  </div>
                )}
                {Object.keys(d.outputs).length > 0 && (
                  <div>
                    <span className="text-muted-foreground">Outputs: </span>
                    <code className="text-xs bg-muted/30 p-1 rounded">{JSON.stringify(d.outputs)}</code>
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      ))}
    </div>
  );
}

// ─── Message Feed ──────────────────────────────────────────────────────────

function MessageFeed({ messages }: { messages: AgentMessage[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length]);

  if (!messages.length)
    return <p className="text-sm text-muted-foreground p-4">No messages yet</p>;

  return (
    <ScrollArea className="h-[500px]" ref={scrollRef}>
      <div className="space-y-2 p-2">
        {messages.map((msg, i) => (
          <motion.div
            key={msg.id || i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex gap-3 p-2 rounded-lg hover:bg-muted/20 transition-colors"
          >
            <div className="flex flex-col items-center gap-1 min-w-0">
              <AgentBadge agentId={msg.from_agent} />
              <ArrowRight className="w-3 h-3 text-muted-foreground" />
              <AgentBadge agentId={msg.to_agent} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-xs">
                  {msg.message_type}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-1 font-mono truncate">
                {JSON.stringify(msg.payload).slice(0, 120)}...
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </ScrollArea>
  );
}

// ─── Verification Gates Panel ──────────────────────────────────────────────

function VerificationPanel({
  gates,
  summary,
}: {
  gates: SessionInfo["verification_gates"];
  summary: AnalysisResult["verification_summary"];
}) {
  return (
    <div className="space-y-4 p-2">
      <div className="grid grid-cols-3 gap-3">
        <Card className="border-green-500/30 bg-green-500/5">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-green-400">{summary.passed}</div>
            <div className="text-xs text-muted-foreground">Passed</div>
          </CardContent>
        </Card>
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-red-400">{summary.failed}</div>
            <div className="text-xs text-muted-foreground">Failed</div>
          </CardContent>
        </Card>
        <Card className="border-yellow-500/30 bg-yellow-500/5">
          <CardContent className="p-3 text-center">
            <div className="text-2xl font-bold text-yellow-400">{summary.needs_review}</div>
            <div className="text-xs text-muted-foreground">Review</div>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-1">
        {gates.map((gate, i) => {
          const StatusIcon = STATUS_ICONS[gate.result] || Clock;
          const color = STATUS_COLORS[gate.result] || "text-gray-400";
          return (
            <div key={i} className="flex items-center gap-2 p-2 rounded hover:bg-muted/20 text-sm">
              <StatusIcon className={`w-4 h-4 ${color}`} />
              <span className="font-mono text-xs">{gate.gate_name}</span>
              <span className="flex-1 text-xs text-muted-foreground truncate">{gate.details}</span>
              <Badge variant="outline" className={`text-xs ${color}`}>
                {gate.result}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Evaluation Metrics ────────────────────────────────────────────────────

function EvaluationPanel({ evaluation }: { evaluation: AnalysisResult["evaluation"] }) {
  if (!evaluation || evaluation.total_metrics === 0)
    return <p className="text-sm text-muted-foreground p-4">No evaluation data</p>;

  return (
    <div className="space-y-3 p-2">
      {Object.entries(evaluation.averages || {}).map(([name, value]) => (
        <div key={name} className="space-y-1">
          <div className="flex justify-between text-sm">
            <span className="font-mono text-muted-foreground">{name}</span>
            <span className="font-mono">{(value * 100).toFixed(1)}%</span>
          </div>
          <Progress value={value * 100} className="h-2" />
        </div>
      ))}
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────

export function AgentDashboard() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<Array<Record<string, unknown>>>([]);
  const [liveEvents, setLiveEvents] = useState<Array<Record<string, unknown>>>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchAgents = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/agents`);
      const data = await res.json();
      setAgents(data.agents || []);
    } catch {
      /* agents will populate on first analysis */
    }
  }, []);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/sessions`);
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch {
      /* ok */
    }
  }, []);

  useEffect(() => {
    fetchAgents();
    fetchSessions();
  }, [fetchAgents, fetchSessions]);

  const connectWs = useCallback((sessionId: string) => {
    if (wsRef.current) wsRef.current.close();
    const ws = new WebSocket(`ws://localhost:8000/agent/ws/${sessionId}`);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLiveEvents((prev) => [...prev.slice(-100), data]);
    };
    wsRef.current = ws;
  }, []);

  const runAnalysis = async () => {
    setLoading(true);
    setLiveEvents([]);
    setResult(null);

    try {
      const resourcesRes = await fetch(`${API_BASE}/resources`);
      const resourcesData = await resourcesRes.json();
      const resources = resourcesData.resources || resourcesData || [];

      const analyzeRes = await fetch(`${API_BASE}/agent/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resources: resources.slice(0, 10) }),
      });
      const analysisResult: AnalysisResult = await analyzeRes.json();
      setResult(analysisResult);

      if (analysisResult.session?.session_id) {
        connectWs(analysisResult.session.session_id);
      }

      fetchAgents();
      fetchSessions();
    } catch (err) {
      console.error("Analysis failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadSession = async (sessionId: string) => {
    try {
      const [sessionRes, traceRes, messagesRes] = await Promise.all([
        fetch(`${API_BASE}/agent/session/${sessionId}`),
        fetch(`${API_BASE}/agent/trace/${sessionId}`),
        fetch(`${API_BASE}/agent/messages/${sessionId}`),
      ]);
      const sessionData = await sessionRes.json();
      const traceData = await traceRes.json();
      const messagesData = await messagesRes.json();

      setResult({
        session: sessionData,
        recommendations: [],
        decisions: [],
        messages: messagesData.messages || [],
        trace: traceData.spans || [],
        interaction_graph: messagesData.interaction_graph || { nodes: [], edges: [] },
        verification_summary: { total_gates: 0, passed: 0, failed: 0, needs_review: 0 },
        evaluation: { total_metrics: 0, averages: {}, benchmark_pass_rate: 0 },
      });

      connectWs(sessionId);
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Brain className="w-6 h-6 text-purple-400" />
            Multi-Agent Intelligence
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Watch AI agents collaborate, critique, and optimize your cloud infrastructure
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-xs">
            {agents.length} agents registered
          </Badge>
          <Button onClick={runAnalysis} disabled={loading} className="gap-2">
            {loading ? (
              <>
                <Activity className="w-4 h-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Run Analysis
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Agent Registry */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {agents.map((agent) => {
          const Icon = AGENT_ICONS[agent.agent_id] || Brain;
          const colorClass = AGENT_COLORS[agent.agent_id] || "bg-gray-500/20 text-gray-400 border-gray-500/30";
          return (
            <motion.div key={agent.agent_id} whileHover={{ scale: 1.03 }}>
              <Card className={`border ${colorClass.split(" ").pop()} bg-card/50`}>
                <CardContent className="p-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon className={`w-4 h-4 ${colorClass.split(" ")[1]}`} />
                    <span className="text-xs font-mono font-medium">{agent.agent_id}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {agent.capabilities.slice(0, 3).map((cap) => (
                      <Badge key={cap} variant="secondary" className="text-[10px]">
                        {cap}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {/* Session Overview */}
      {result?.session && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg flex items-center gap-2">
                  <Activity className="w-5 h-5" />
                  Session: {result.session.session_id.slice(0, 8)}...
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={
                      result.session.status === "completed"
                        ? "text-green-400 border-green-500/30"
                        : result.session.status === "failed"
                          ? "text-red-400 border-red-500/30"
                          : "text-yellow-400 border-yellow-500/30"
                    }
                  >
                    {result.session.status}
                  </Badge>
                  <Badge variant="secondary">{result.session.resource_count} resources</Badge>
                  <Badge variant="secondary">{result.session.recommendation_count} recommendations</Badge>
                  <Badge variant="secondary">{result.session.decision_count} decisions</Badge>
                  <Badge variant="secondary">{result.session.message_count} messages</Badge>
                </div>
              </div>
            </CardHeader>
          </Card>
        </motion.div>
      )}

      {/* Main Tabs */}
      <Tabs defaultValue="trace" className="space-y-4">
        <TabsList className="grid grid-cols-7 w-full">
          <TabsTrigger value="trace" className="text-xs gap-1">
            <BarChart3 className="w-3 h-3" /> Trace
          </TabsTrigger>
          <TabsTrigger value="agents" className="text-xs gap-1">
            <Network className="w-3 h-3" /> Agents
          </TabsTrigger>
          <TabsTrigger value="decisions" className="text-xs gap-1">
            <Brain className="w-3 h-3" /> Decisions
          </TabsTrigger>
          <TabsTrigger value="messages" className="text-xs gap-1">
            <MessageSquare className="w-3 h-3" /> Messages
          </TabsTrigger>
          <TabsTrigger value="gates" className="text-xs gap-1">
            <Shield className="w-3 h-3" /> Gates
          </TabsTrigger>
          <TabsTrigger value="eval" className="text-xs gap-1">
            <Zap className="w-3 h-3" /> Eval
          </TabsTrigger>
          <TabsTrigger value="sessions" className="text-xs gap-1">
            <Clock className="w-3 h-3" /> History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="trace">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Execution Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <TraceTimeline spans={result?.trace || []} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="agents">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Agent Interaction Graph</CardTitle>
            </CardHeader>
            <CardContent>
              <InteractionGraph
                graph={result?.interaction_graph || { nodes: [], edges: [] }}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="decisions">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Decision Trail</CardTitle>
            </CardHeader>
            <CardContent>
              <DecisionLog decisions={result?.decisions || []} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="messages">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Agent Communication Feed</CardTitle>
            </CardHeader>
            <CardContent>
              <MessageFeed messages={result?.messages || []} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="gates">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Verification Gates</CardTitle>
            </CardHeader>
            <CardContent>
              <VerificationPanel
                gates={result?.session?.verification_gates || []}
                summary={
                  result?.verification_summary || {
                    total_gates: 0,
                    passed: 0,
                    failed: 0,
                    needs_review: 0,
                  }
                }
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="eval">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Evaluation Metrics</CardTitle>
            </CardHeader>
            <CardContent>
              <EvaluationPanel
                evaluation={
                  result?.evaluation || {
                    total_metrics: 0,
                    averages: {},
                    benchmark_pass_rate: 0,
                  }
                }
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sessions">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Session History</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {sessions.map((s, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 rounded-lg border border-border/50 hover:bg-muted/20 cursor-pointer transition-colors"
                    onClick={() => loadSession(String(s.session_id))}
                  >
                    <div className="flex items-center gap-3">
                      <Eye className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm font-mono">{String(s.session_id).slice(0, 12)}...</span>
                      <Badge variant="outline" className="text-xs">
                        {String(s.status)}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{String(s.resource_count || 0)} resources</span>
                      <span>{String(s.recommendation_count || 0)} recs</span>
                    </div>
                  </div>
                ))}
                {sessions.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center p-4">
                    No sessions yet. Run an analysis to get started.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Live Events Panel */}
      {liveEvents.length > 0 && (
        <Card className="border-purple-500/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Activity className="w-4 h-4 text-purple-400 animate-pulse" />
              Live Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-32">
              <div className="space-y-1">
                {liveEvents.slice(-10).map((evt, i) => (
                  <div key={i} className="text-xs font-mono text-muted-foreground">
                    <span className="text-purple-400">[{String(evt.event)}]</span>{" "}
                    {JSON.stringify(evt.data).slice(0, 100)}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
