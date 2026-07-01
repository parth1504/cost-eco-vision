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
  Zap,
  Eye,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  Server,
  Database,
  HardDrive,
  BarChart3,
  GitBranch,
  Layers,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";

const API_BASE = "http://localhost:8000";

// ─── Types ────────────────────────────────────────────────────────────────

interface GraphNode {
  id: string;
  type: string;
}

interface GraphEdge {
  source: string;
  target: string;
  conditional: boolean;
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
  from_agent: string;
  to_agent: string;
  content: string;
  timestamp: number;
}

interface Decision {
  agent: string;
  action: string;
  reasoning: string;
  timestamp: number;
}

interface VerificationGate {
  gate_name: string;
  result: string;
  details: string;
  threshold?: number;
  actual_value?: number;
}

interface Correlation {
  type: string;
  title: string;
  description: string;
  confidence: number;
  combined_savings?: number;
  resources_involved?: string[];
}

interface SessionInfo {
  session_id: string;
  trace_id: string;
  status: string;
  resource_count: number;
  recommendation_count: number;
  message_count: number;
  decision_count: number;
  duration_ms?: number;
  error?: string;
}

interface AnalysisResult {
  session: SessionInfo;
  recommendations: Array<Record<string, unknown>>;
  decisions: Decision[];
  messages: AgentMessage[];
  correlations: Correlation[];
  verification_summary: {
    total_gates: number;
    passed: number;
    failed: number;
    needs_review: number;
  };
  verification_gates: VerificationGate[];
  evaluation: {
    total_metrics: number;
    averages: Record<string, number>;
    benchmark_pass_rate: number;
    benchmark_count: number;
  };
}

// ─── Constants ────────────────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  supervisor: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  ec2_specialist: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  s3_specialist: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  dynamodb_specialist: "bg-green-500/20 text-green-400 border-green-500/30",
  critique: "bg-red-500/20 text-red-400 border-red-500/30",
  correlation: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  correlate: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  refine: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  verify: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  evaluate: "bg-indigo-500/20 text-indigo-400 border-indigo-500/30",
  aggregate: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  aggregator: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  dispatch: "bg-violet-500/20 text-violet-400 border-violet-500/30",
};

const AGENT_ICONS: Record<string, typeof Brain> = {
  supervisor: Brain,
  ec2_specialist: Server,
  s3_specialist: HardDrive,
  dynamodb_specialist: Database,
  critique: Shield,
  correlation: Network,
  correlate: Network,
  refine: GitBranch,
  verify: CheckCircle,
  evaluate: BarChart3,
  aggregate: Layers,
  dispatch: Zap,
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

// ─── Components ───────────────────────────────────────────────────────────

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

function GraphTopology({
  nodes,
  edges,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
}) {
  const agentNodes = nodes.filter((n) => n.type === "agent");
  if (!agentNodes.length)
    return <p className="text-sm text-muted-foreground p-4">No graph data</p>;

  return (
    <div className="p-4 space-y-4">
      <div className="flex flex-wrap gap-3 justify-center">
        {agentNodes.map((node) => (
          <motion.div
            key={node.id}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            whileHover={{ scale: 1.05 }}
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
      <div className="space-y-1 max-h-64 overflow-y-auto">
        {edges.map((edge, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex items-center gap-2 text-xs text-muted-foreground font-mono"
          >
            <AgentBadge agentId={edge.source} />
            <ArrowRight className="w-3 h-3" />
            <AgentBadge agentId={edge.target} />
            {edge.conditional && (
              <Badge variant="secondary" className="text-[10px]">
                conditional
              </Badge>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

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
          </button>
          <AnimatePresence>
            {expanded.has(i) && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="border-t border-border/30 bg-muted/10 px-4 py-3 text-sm"
              >
                <span className="text-muted-foreground">Reasoning: </span>
                <span>{d.reasoning}</span>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      ))}
    </div>
  );
}

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
            key={i}
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
              <p className="text-sm">{msg.content}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </ScrollArea>
  );
}

function VerificationPanel({
  gates,
  summary,
}: {
  gates: VerificationGate[];
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

function CorrelationsPanel({ correlations }: { correlations: Correlation[] }) {
  if (!correlations.length)
    return <p className="text-sm text-muted-foreground p-4">No cross-resource correlations found</p>;

  return (
    <div className="space-y-3 p-2">
      {correlations.map((c, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.1 }}
        >
          <Card className="border-cyan-500/30">
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium">{c.title}</h4>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-xs">{c.type}</Badge>
                  <Badge variant="outline" className="text-xs">{(c.confidence * 100).toFixed(0)}%</Badge>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">{c.description}</p>
              {c.combined_savings != null && c.combined_savings > 0 && (
                <div className="text-sm font-mono text-green-400">
                  Combined savings: ${c.combined_savings.toFixed(2)}/mo
                </div>
              )}
            </CardContent>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

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
      {evaluation.benchmark_count > 0 && (
        <div className="pt-2 border-t border-border/30">
          <div className="flex justify-between text-sm">
            <span className="font-mono text-muted-foreground">Benchmark Pass Rate</span>
            <span className="font-mono">{(evaluation.benchmark_pass_rate * 100).toFixed(1)}%</span>
          </div>
          <Progress value={evaluation.benchmark_pass_rate * 100} className="h-2 mt-1" />
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────

export function AgentDashboard() {
  const [graphTopology, setGraphTopology] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({
    nodes: [],
    edges: [],
  });
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<Array<Record<string, unknown>>>([]);
  const [liveEvents, setLiveEvents] = useState<Array<Record<string, unknown>>>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchGraph = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/graph`);
      const data = await res.json();
      setGraphTopology({ nodes: data.nodes || [], edges: data.edges || [] });
    } catch {
      /* graph will populate on first load */
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
    fetchGraph();
    fetchSessions();
  }, [fetchGraph, fetchSessions]);

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

      fetchGraph();
      fetchSessions();
    } catch (err) {
      console.error("Analysis failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadSession = async (sessionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/agent/session/${sessionId}`);
      const data = await res.json();
      if (data.error) return;

      setResult({
        session: {
          session_id: data.session_id || sessionId,
          trace_id: data.trace_id || "",
          status: data.status || "unknown",
          resource_count: data.resource_count || 0,
          recommendation_count: data.recommendation_count || 0,
          message_count: data.message_count || 0,
          decision_count: data.decision_count || 0,
        },
        recommendations: data.recommendations || [],
        decisions: data.decisions || [],
        messages: data.messages || [],
        correlations: data.correlations || [],
        verification_summary: data.verification_summary || { total_gates: 0, passed: 0, failed: 0, needs_review: 0 },
        verification_gates: data.verification_gates || [],
        evaluation: data.evaluation || { total_metrics: 0, averages: {}, benchmark_pass_rate: 0, benchmark_count: 0 },
      });

      connectWs(sessionId);
    } catch (err) {
      console.error("Failed to load session:", err);
    }
  };

  const agentNodeCount = graphTopology.nodes.filter((n) => n.type === "agent").length;

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
            LangGraph-powered agents collaborate to optimize your cloud infrastructure
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="text-xs gap-1">
            <GitBranch className="w-3 h-3" />
            {agentNodeCount} nodes in graph
          </Badge>
          <Badge variant="outline" className="text-xs gap-1">
            <ExternalLink className="w-3 h-3" />
            LangSmith
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
                  {result.session.duration_ms && (
                    <Badge variant="outline" className="text-xs">
                      {(result.session.duration_ms / 1000).toFixed(1)}s
                    </Badge>
                  )}
                </div>
              </div>
            </CardHeader>
          </Card>
        </motion.div>
      )}

      {/* Main Tabs */}
      <Tabs defaultValue="graph" className="space-y-4">
        <TabsList className="grid grid-cols-8 w-full">
          <TabsTrigger value="graph" className="text-xs gap-1">
            <GitBranch className="w-3 h-3" /> Graph
          </TabsTrigger>
          <TabsTrigger value="trace" className="text-xs gap-1">
            <BarChart3 className="w-3 h-3" /> Trace
          </TabsTrigger>
          <TabsTrigger value="decisions" className="text-xs gap-1">
            <Brain className="w-3 h-3" /> Decisions
          </TabsTrigger>
          <TabsTrigger value="messages" className="text-xs gap-1">
            <MessageSquare className="w-3 h-3" /> Messages
          </TabsTrigger>
          <TabsTrigger value="correlations" className="text-xs gap-1">
            <Network className="w-3 h-3" /> Correlations
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

        <TabsContent value="graph">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <GitBranch className="w-4 h-4" />
                LangGraph Topology
              </CardTitle>
            </CardHeader>
            <CardContent>
              <GraphTopology nodes={graphTopology.nodes} edges={graphTopology.edges} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trace">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Execution Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <TraceTimeline spans={[]} />
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

        <TabsContent value="correlations">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Cross-Resource Correlations</CardTitle>
            </CardHeader>
            <CardContent>
              <CorrelationsPanel correlations={result?.correlations || []} />
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
                gates={result?.verification_gates || []}
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
                    benchmark_count: 0,
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
