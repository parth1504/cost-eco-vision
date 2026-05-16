import { useState, useEffect, useMemo, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock, CheckCircle, AlertTriangle, Activity, FileText, Lightbulb,
  RefreshCw, Sparkles, Network, ArrowRight, ChevronDown, ChevronRight,
  Zap, Search, Eye, Shield, Server, Database, Globe, Layers
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";

const API = "http://localhost:8000";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

type IncidentSummary = {
  incident_id: string;
  status: string;
  severity: string;
  created_at: string;
  member_alert_ids: string[];
  resources_affected: string[];
  title: string;
  source_count?: number;
};

type TimelineEvent = {
  id: string;
  timestamp: string;
  type: string;
  source?: string;
  message: string;
  severity: string;
};

type IncidentDetail = {
  incident_id: string;
  status: string;
  investigating_at?: string | null;
  mitigated_at?: string | null;
  resolved_at?: string | null;
  timeline: TimelineEvent[];
  rootCause: any | null;
  checklist: any[];
  generated_at: string;
};

type LifecycleStatus = "open" | "investigating" | "mitigated" | "resolved";

type ServiceNode = {
  id: string;
  name: string;
  type: "service" | "database" | "external" | "infra";
  status: "healthy" | "degraded" | "failing";
  alertCount: number;
  alerts: TimelineEvent[];
  firstFailure?: string;
  isRootCause?: boolean;
};

type ServiceEdge = {
  from: string;
  to: string;
  label?: string;
};

const STATUS_LABELS: Record<LifecycleStatus, string> = {
  open: "Open",
  investigating: "Investigating",
  mitigated: "Mitigated",
  resolved: "Resolved",
};

const STATUS_COLORS: Record<LifecycleStatus, string> = {
  open: "bg-destructive/10 text-destructive border-destructive/20",
  investigating: "bg-warning/10 text-warning border-warning/20",
  mitigated: "bg-primary/10 text-primary border-primary/20",
  resolved: "bg-success/10 text-success border-success/20",
};

const NEXT_STATES: Record<LifecycleStatus, LifecycleStatus[]> = {
  open: ["investigating", "mitigated", "resolved"],
  investigating: ["mitigated", "resolved", "open"],
  mitigated: ["resolved", "investigating", "open"],
  resolved: ["open", "investigating"],
};

// ─── Service Graph Builder ──────────────────────────────────────────────────

function buildServiceGraph(timeline: TimelineEvent[]): { nodes: ServiceNode[]; edges: ServiceEdge[] } {
  const serviceMap = new Map<string, ServiceNode>();

  for (const event of timeline) {
    const source = event.source || "Unknown";
    if (!serviceMap.has(source)) {
      serviceMap.set(source, {
        id: source,
        name: source,
        type: inferServiceType(source),
        status: "healthy",
        alertCount: 0,
        alerts: [],
      });
    }
    const node = serviceMap.get(source)!;
    node.alertCount++;
    node.alerts.push(event);

    if (!node.firstFailure || event.timestamp < node.firstFailure) {
      node.firstFailure = event.timestamp;
    }

    const sev = (event.severity || "").toLowerCase();
    if (sev === "critical" || sev === "high") {
      node.status = "failing";
    } else if (sev === "warning" && node.status !== "failing") {
      node.status = "degraded";
    }
  }

  const nodes = Array.from(serviceMap.values());
  nodes.sort((a, b) => (a.firstFailure || "z").localeCompare(b.firstFailure || "z"));

  if (nodes.length > 0) {
    nodes[0].isRootCause = true;
  }

  const edges: ServiceEdge[] = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    edges.push({
      from: nodes[i].id,
      to: nodes[i + 1].id,
      label: "triggers",
    });
  }

  return { nodes, edges };
}

function inferServiceType(source: string): "service" | "database" | "external" | "infra" {
  const s = source.toLowerCase();
  if (s.includes("rds") || s.includes("dynamo") || s.includes("database") || s.includes("redis")) return "database";
  if (s.includes("api") || s.includes("gateway") || s.includes("external")) return "external";
  if (s.includes("ec2") || s.includes("lambda") || s.includes("ecs") || s.includes("infra")) return "infra";
  return "service";
}

// ─── Expandable Section ─────────────────────────────────────────────────────

function ExpandableSection({ title, icon: Icon, children, defaultOpen = false, badge }: any) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 p-3 hover:bg-muted/30 transition-colors text-left">
        {Icon && <Icon className="h-4 w-4 text-muted-foreground" />}
        <span className="text-sm font-medium flex-1">{title}</span>
        {badge}
        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }}>
            <div className="p-3 pt-0 border-t border-border">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Service Dependency Graph (Visual) ──────────────────────────────────────

function ServiceDependencyGraph({ nodes, edges, onNodeClick, selectedNode }: {
  nodes: ServiceNode[];
  edges: ServiceEdge[];
  onNodeClick: (node: ServiceNode) => void;
  selectedNode: string | null;
}) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case "failing": return "border-destructive bg-destructive/10 shadow-destructive/20 shadow-lg";
      case "degraded": return "border-warning bg-warning/10 shadow-warning/20 shadow-md";
      default: return "border-success/50 bg-success/5";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "database": return <Database className="h-4 w-4" />;
      case "external": return <Globe className="h-4 w-4" />;
      case "infra": return <Server className="h-4 w-4" />;
      default: return <Layers className="h-4 w-4" />;
    }
  };

  if (nodes.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8 text-sm">
        No service data available for this incident.
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Graph visualization */}
      <div className="flex flex-wrap items-start gap-3 justify-center py-4">
        {nodes.map((node, i) => (
          <div key={node.id} className="flex items-center gap-2">
            {/* Node */}
            <button
              onClick={() => onNodeClick(node)}
              className={`relative p-3 rounded-xl border-2 transition-all min-w-[140px] text-left ${getStatusColor(node.status)} ${
                selectedNode === node.id ? "ring-2 ring-primary ring-offset-2" : ""
              }`}
            >
              {/* Order badge */}
              <div className="absolute -top-2 -left-2 h-5 w-5 rounded-full bg-foreground text-background text-[10px] font-bold flex items-center justify-center">
                {i + 1}
              </div>
              {/* Root cause indicator */}
              {node.isRootCause && (
                <div className="absolute -top-2 -right-2 px-1.5 py-0.5 rounded bg-destructive text-destructive-foreground text-[9px] font-bold">
                  ROOT
                </div>
              )}
              <div className="flex items-center gap-2 mb-1">
                {getTypeIcon(node.type)}
                <span className="text-xs font-semibold truncate">{node.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={node.status === "failing" ? "destructive" : node.status === "degraded" ? "secondary" : "default"} className="text-[9px] px-1.5">
                  {node.status}
                </Badge>
                {node.alertCount > 0 && (
                  <span className="text-[10px] text-muted-foreground">{node.alertCount} alert{node.alertCount > 1 ? "s" : ""}</span>
                )}
              </div>
            </button>

            {/* Edge arrow */}
            {i < nodes.length - 1 && (
              <div className="flex flex-col items-center gap-0.5">
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <span className="text-[9px] text-muted-foreground">{edges[i]?.label}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-2 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-1"><div className="h-2.5 w-2.5 rounded border-2 border-destructive bg-destructive/20" />Failing</div>
        <div className="flex items-center gap-1"><div className="h-2.5 w-2.5 rounded border-2 border-warning bg-warning/20" />Degraded</div>
        <div className="flex items-center gap-1"><div className="h-2.5 w-2.5 rounded border-2 border-success/50 bg-success/10" />Healthy</div>
        <div className="flex items-center gap-1"><div className="h-3 px-1 rounded bg-destructive text-destructive-foreground text-[8px] font-bold flex items-center">ROOT</div>Root Cause</div>
      </div>
    </div>
  );
}

// ─── Propagation Path ───────────────────────────────────────────────────────

function PropagationPath({ nodes }: { nodes: ServiceNode[] }) {
  if (nodes.length < 2) return null;

  return (
    <div className="space-y-2">
      {nodes.map((node, i) => (
        <motion.div
          key={node.id}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.1 }}
          className="flex items-start gap-3"
        >
          <div className="flex flex-col items-center">
            <div className={`h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
              node.isRootCause ? "bg-destructive text-destructive-foreground" : "bg-muted text-muted-foreground"
            }`}>
              {i + 1}
            </div>
            {i < nodes.length - 1 && <div className="w-px h-6 bg-border" />}
          </div>
          <div className="flex-1 pb-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{node.name}</span>
              <Badge variant={node.isRootCause ? "destructive" : "secondary"} className="text-[10px]">
                {node.isRootCause ? "Root Cause" : "Downstream Symptom"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {node.isRootCause
                ? `First failure at ${node.firstFailure ? new Date(node.firstFailure).toLocaleTimeString() : "unknown"} — ${node.alertCount} alert(s) originated here`
                : `Affected ${node.firstFailure ? new Date(node.firstFailure).toLocaleTimeString() : "later"} — ${node.alertCount} cascaded alert(s)`
              }
            </p>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ─── RCA Verification Steps ─────────────────────────────────────────────────

function RCAVerification({ nodes, rootCause }: { nodes: ServiceNode[]; rootCause: any }) {
  const rootNode = nodes.find(n => n.isRootCause);
  const downstreamNodes = nodes.filter(n => !n.isRootCause);

  const verifications = [
    {
      question: "Did this service fail before others?",
      answer: rootNode
        ? `Yes — ${rootNode.name} first alerted at ${rootNode.firstFailure ? new Date(rootNode.firstFailure).toLocaleTimeString() : "N/A"}, before all downstream services.`
        : "Unable to determine temporal ordering.",
      passed: !!rootNode?.firstFailure,
      icon: Clock,
    },
    {
      question: "Are downstream failures temporally after?",
      answer: downstreamNodes.length > 0
        ? `Yes — ${downstreamNodes.length} service(s) started failing after the root cause: ${downstreamNodes.map(n => n.name).join(", ")}.`
        : "No downstream failures detected.",
      passed: downstreamNodes.length > 0,
      icon: ArrowRight,
    },
    {
      question: "Are there error logs or anomalies at the root?",
      answer: rootNode && rootNode.alertCount > 0
        ? `Yes — ${rootNode.alertCount} alert(s) detected at ${rootNode.name} including: "${rootNode.alerts[0]?.message?.slice(0, 80)}..."`
        : "No specific error signals found.",
      passed: (rootNode?.alertCount || 0) > 0,
      icon: AlertTriangle,
    },
    {
      question: "Is there a recent code or infra change?",
      answer: rootCause?.contributingFactors?.length > 0
        ? `AI identified ${rootCause.contributingFactors.length} contributing factor(s) that may involve recent changes.`
        : "No recent change signals found — may require manual investigation.",
      passed: rootCause?.contributingFactors?.length > 0,
      icon: Search,
    },
  ];

  return (
    <div className="space-y-3">
      {verifications.map((v, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08 }}
          className="flex items-start gap-3 p-3 rounded-lg bg-muted/20"
        >
          <div className={`p-1.5 rounded ${v.passed ? "bg-success/10" : "bg-muted"}`}>
            <v.icon className={`h-3.5 w-3.5 ${v.passed ? "text-success" : "text-muted-foreground"}`} />
          </div>
          <div className="flex-1">
            <p className="text-xs font-medium text-foreground">{v.question}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{v.answer}</p>
          </div>
          {v.passed ? (
            <CheckCircle className="h-4 w-4 text-success flex-shrink-0" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          )}
        </motion.div>
      ))}
    </div>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────

export function IncidentCoordinator() {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [statusUpdating, setStatusUpdating] = useState(false);
  const [checklist, setChecklist] = useState<any[]>([]);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const { toast } = useToast();

  // Build the service graph from timeline
  const { nodes: serviceNodes, edges: serviceEdges } = useMemo(
    () => buildServiceGraph(detail?.timeline || []),
    [detail?.timeline]
  );

  const selectedService = useMemo(
    () => serviceNodes.find(n => n.id === selectedNode) || null,
    [serviceNodes, selectedNode]
  );

  const transitionStatus = async (next: LifecycleStatus) => {
    if (!selectedId || !detail) return;
    setStatusUpdating(true);
    try {
      const res = await fetch(`${API}/incident/${selectedId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      if (!res.ok) throw new Error(await res.text());
      await loadDetail(selectedId);
      await loadIncidents(false);
      toast({ title: "Status updated", description: `Incident is now ${STATUS_LABELS[next]}.` });
    } catch (err) {
      toast({ title: "Couldn't update status", description: String(err), variant: "destructive" });
    } finally {
      setStatusUpdating(false);
    }
  };

  const loadIncidents = async (autoSelect = true) => {
    setLoadingList(true);
    try {
      const res = await fetch(`${API}/incident`);
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const data: IncidentSummary[] = await res.json();
      setIncidents(data);
      const grouped = data.filter((i) => i.member_alert_ids.length >= 2);
      if (autoSelect && grouped.length > 0 && !selectedId) {
        setSelectedId(grouped[0].incident_id);
      }
    } catch (err) {
      toast({ title: "Couldn't load incidents", description: String(err), variant: "destructive" });
    } finally {
      setLoadingList(false);
    }
  };

  const loadDetail = async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await fetch(`${API}/incident/${id}`);
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const data: IncidentDetail = await res.json();
      setDetail(data);
      setChecklist(data.checklist ?? []);
      setSelectedNode(null);
    } catch (err) {
      toast({ title: "Couldn't load incident", description: String(err), variant: "destructive" });
    } finally {
      setLoadingDetail(false);
    }
  };

  const runAnalysis = async (force = false) => {
    if (!selectedId) return;
    setAnalyzing(true);
    try {
      const res = await fetch(`${API}/incident/${selectedId}/analyze${force ? "?force=true" : ""}`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      await loadDetail(selectedId);
      toast({ title: "Analysis ready", description: "Root cause + propagation path generated." });
    } catch (err) {
      toast({ title: "Analysis failed", description: String(err), variant: "destructive" });
    } finally {
      setAnalyzing(false);
    }
  };

  const refreshCorrelation = async () => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API}/incident/refresh`, { method: "POST" });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      const fresh: IncidentSummary[] = await res.json();
      setIncidents(fresh);
      const grouped = fresh.filter((i) => i.member_alert_ids.length >= 2);
      toast({ title: "Correlation refreshed", description: `Found ${grouped.length} correlated incident(s).` });
      if (grouped.length > 0) setSelectedId(grouped[0].incident_id);
      else { setSelectedId(null); setDetail(null); }
    } catch (err) {
      toast({ title: "Refresh failed", description: String(err), variant: "destructive" });
    } finally {
      setRefreshing(false);
    }
  };

  const runLayer2 = async () => {
    setRefreshing(true);
    try {
      const res = await fetch(`${API}/incident/correlate-l2`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      toast({
        title: "AI cross-service correlation complete",
        description: `${result.joins_applied ?? 0} join(s), ${result.new_incidents_created ?? 0} new incident(s).`,
      });
      await loadIncidents(false);
    } catch (err) {
      toast({ title: "AI correlation failed", description: String(err), variant: "destructive" });
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => { loadIncidents(); }, []);
  useEffect(() => { if (selectedId) loadDetail(selectedId); }, [selectedId]);

  const groupedIncidents = useMemo(
    () => incidents.filter(i => i.member_alert_ids.length >= 2),
    [incidents]
  );

  const selectedSummary = useMemo(
    () => groupedIncidents.find(i => i.incident_id === selectedId) ?? null,
    [groupedIncidents, selectedId]
  );

  const getSeverityColor = (severity: string) => {
    switch ((severity || "").toLowerCase()) {
      case "critical": return "status-critical";
      case "high":
      case "warning": return "status-warning";
      default: return "bg-muted text-muted-foreground";
    }
  };

  const completedTasks = checklist.filter(item => item.completed).length;
  const progressPercentage = checklist.length > 0 ? (completedTasks / checklist.length) * 100 : 0;

  if (loadingList) {
    return (
      <div className="flex items-center justify-center py-12 gap-2 text-muted-foreground">
        <RefreshCw className="h-4 w-4 animate-spin" />
        <span>Loading incidents...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Incident Picker */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="h-5 w-5 text-primary" />
                <span>Active Incidents</span>
                <Badge variant="outline">{groupedIncidents.length}</Badge>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={refreshCorrelation} disabled={refreshing}>
                  <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
                  Correlate
                </Button>
                <Button size="sm" variant="outline" onClick={runLayer2} disabled={refreshing || groupedIncidents.length === 0}>
                  <Sparkles className={`h-4 w-4 mr-2 ${refreshing ? "animate-pulse" : ""}`} />
                  AI Cross-Service
                </Button>
              </div>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {groupedIncidents.length === 0 ? (
              <div className="text-sm text-muted-foreground py-4 text-center">
                No correlated incidents. Click <strong>Correlate</strong> to group related alerts.
              </div>
            ) : (
              <div className="space-y-2">
                {groupedIncidents.map(inc => (
                  <button
                    key={inc.incident_id}
                    onClick={() => setSelectedId(inc.incident_id)}
                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                      inc.incident_id === selectedId ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center space-x-2">
                        <Badge className={getSeverityColor(inc.severity)}>{inc.severity}</Badge>
                        <span className="text-sm font-medium">{inc.title}</span>
                      </div>
                      <span className="text-xs text-muted-foreground font-mono">{inc.incident_id}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {inc.member_alert_ids.length} alert(s) · {inc.resources_affected.length} resource(s) · {new Date(inc.created_at).toLocaleString()}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Detail View */}
      {!selectedId ? null : loadingDetail || !detail ? (
        <div className="flex items-center justify-center py-8 gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span>Loading incident detail...</span>
        </div>
      ) : (
        <>
          {/* Status Bar */}
          <motion.div variants={itemVariants}>
            <Card className="dashboard-card">
              <CardContent className="pt-4 pb-4">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <Badge className={STATUS_COLORS[(detail.status as LifecycleStatus) || "open"]}>
                      {STATUS_LABELS[(detail.status as LifecycleStatus) || "open"]}
                    </Badge>
                    <span className="text-sm font-medium">{selectedSummary?.title}</span>
                    <Badge variant="outline" className="text-[10px] font-mono">{selectedId}</Badge>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(NEXT_STATES[(detail.status as LifecycleStatus) || "open"] || []).map(next => (
                      <Button key={next} size="sm" variant="outline" onClick={() => transitionStatus(next)} disabled={statusUpdating}>
                        {next === "resolved" && <CheckCircle className="h-3 w-3 mr-1" />}
                        {next === "investigating" && <Activity className="h-3 w-3 mr-1" />}
                        Mark {STATUS_LABELS[next]}
                      </Button>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>

          {/* Main Tabs: Graph | Timeline | RCA */}
          <motion.div variants={itemVariants}>
            <Tabs defaultValue="graph" className="w-full">
              <TabsList className="grid w-full grid-cols-3 max-w-lg">
                <TabsTrigger value="graph" className="gap-1.5">
                  <Network className="h-3.5 w-3.5" />Dependency Graph
                </TabsTrigger>
                <TabsTrigger value="timeline" className="gap-1.5">
                  <Clock className="h-3.5 w-3.5" />Timeline
                </TabsTrigger>
                <TabsTrigger value="rca" className="gap-1.5">
                  <Lightbulb className="h-3.5 w-3.5" />Root Cause
                </TabsTrigger>
              </TabsList>

              {/* ─── GRAPH TAB ──────────────────────────────────────── */}
              <TabsContent value="graph" className="mt-4 space-y-4">
                <Card className="dashboard-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Network className="h-4 w-4 text-primary" />
                      Service Dependency Map
                    </CardTitle>
                    <CardDescription>
                      Click a service to inspect its alerts. Numbered by failure order.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ServiceDependencyGraph
                      nodes={serviceNodes}
                      edges={serviceEdges}
                      onNodeClick={(node) => setSelectedNode(selectedNode === node.id ? null : node.id)}
                      selectedNode={selectedNode}
                    />
                  </CardContent>
                </Card>

                {/* Selected node detail */}
                <AnimatePresence>
                  {selectedService && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                    >
                      <Card className="dashboard-card border-primary/30">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm flex items-center gap-2">
                            <Eye className="h-4 w-4 text-primary" />
                            {selectedService.name} — {selectedService.alertCount} Alert(s)
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2 max-h-48 overflow-y-auto">
                            {selectedService.alerts.map((alert, i) => (
                              <div key={i} className="flex items-start gap-2 p-2 bg-muted/20 rounded text-xs">
                                <Badge className={getSeverityColor(alert.severity)} variant="secondary">
                                  {alert.severity}
                                </Badge>
                                <div className="flex-1">
                                  <p className="font-medium">{alert.message}</p>
                                  <p className="text-muted-foreground mt-0.5">
                                    {alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString() : ""}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Propagation path */}
                <Card className="dashboard-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Zap className="h-4 w-4 text-warning" />
                      Failure Propagation Path
                    </CardTitle>
                    <CardDescription>
                      How the failure cascaded from root cause to downstream services
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <PropagationPath nodes={serviceNodes} />
                  </CardContent>
                </Card>
              </TabsContent>

              {/* ─── TIMELINE TAB ───────────────────────────────────── */}
              <TabsContent value="timeline" className="mt-4">
                <Card className="dashboard-card">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Clock className="h-4 w-4 text-primary" />
                      Event Timeline
                    </CardTitle>
                    <CardDescription>
                      All events in chronological order, grouped by service
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    {detail.timeline.length === 0 ? (
                      <div className="text-sm text-muted-foreground py-4">No events recorded.</div>
                    ) : (
                      <div className="relative">
                        <div className="absolute left-5 top-0 bottom-0 w-px bg-border"></div>
                        <div className="space-y-4">
                          {detail.timeline.map((event, index) => {
                            const isFirst = index === 0;
                            return (
                              <motion.div
                                key={event.id}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.05 }}
                                className="relative flex items-start space-x-4 pl-1"
                              >
                                <div className={`flex items-center justify-center w-9 h-9 rounded-full z-10 border-2 ${
                                  isFirst ? "bg-destructive/10 border-destructive" : "bg-background border-border"
                                }`}>
                                  {isFirst ? <Zap className="h-3.5 w-3.5 text-destructive" /> : <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" />}
                                </div>
                                <div className="flex-1 min-w-0 pb-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <Badge variant="outline" className="text-[10px]">{event.source || event.type}</Badge>
                                    <Badge className={getSeverityColor(event.severity)}>{event.severity}</Badge>
                                    <span className="text-[10px] text-muted-foreground">
                                      {event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ""}
                                    </span>
                                    {isFirst && <Badge variant="destructive" className="text-[9px]">First Failure</Badge>}
                                  </div>
                                  <p className="text-sm mt-1 text-foreground">{event.message}</p>
                                </div>
                              </motion.div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* ─── RCA TAB ────────────────────────────────────────── */}
              <TabsContent value="rca" className="mt-4 space-y-4">
                {/* AI Analysis trigger */}
                {!detail.rootCause && (
                  <Card className="dashboard-card">
                    <CardContent className="pt-6 text-center space-y-3">
                      <Lightbulb className="h-8 w-8 text-warning mx-auto" />
                      <p className="text-sm text-muted-foreground">
                        Run the AI agent to identify root cause with verification steps.
                      </p>
                      <Button onClick={() => runAnalysis(false)} disabled={analyzing}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${analyzing ? "animate-spin" : ""}`} />
                        {analyzing ? "Reasoning..." : "Run Root Cause Analysis"}
                      </Button>
                    </CardContent>
                  </Card>
                )}

                {/* Verification Steps */}
                <Card className="dashboard-card">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Shield className="h-4 w-4 text-primary" />
                      Verification Steps
                    </CardTitle>
                    <CardDescription>
                      Structured reasoning — why we believe this is the root cause
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <RCAVerification nodes={serviceNodes} rootCause={detail.rootCause} />
                  </CardContent>
                </Card>

                {/* AI Conclusion */}
                {detail.rootCause && (
                  <Card className="dashboard-card border-primary/20">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base flex items-center gap-2">
                          <Lightbulb className="h-4 w-4 text-warning" />
                          AI Root Cause Conclusion
                        </CardTitle>
                        <div className="flex items-center gap-2">
                          {detail.rootCause.confidence != null && (
                            <Badge variant="outline">{detail.rootCause.confidence}% confidence</Badge>
                          )}
                          <Button size="sm" variant="ghost" onClick={() => runAnalysis(true)} disabled={analyzing}>
                            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${analyzing ? "animate-spin" : ""}`} />
                            Re-analyze
                          </Button>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {detail.rootCause.primaryCause && (
                        <div className="p-3 bg-destructive/5 border border-destructive/20 rounded-lg">
                          <p className="text-[10px] text-muted-foreground uppercase font-medium mb-1">Primary Cause</p>
                          <p className="text-sm font-medium">{detail.rootCause.primaryCause}</p>
                        </div>
                      )}

                      {Array.isArray(detail.rootCause.contributingFactors) && detail.rootCause.contributingFactors.length > 0 && (
                        <ExpandableSection title="Contributing Factors" icon={Layers} defaultOpen>
                          <div className="space-y-1.5 mt-2">
                            {detail.rootCause.contributingFactors.map((f: string, i: number) => (
                              <div key={i} className="flex items-start gap-2 text-xs">
                                <ArrowRight className="h-3 w-3 mt-0.5 text-warning flex-shrink-0" />
                                <span>{f}</span>
                              </div>
                            ))}
                          </div>
                        </ExpandableSection>
                      )}

                      {Array.isArray(detail.rootCause.immediateActions) && detail.rootCause.immediateActions.length > 0 && (
                        <ExpandableSection title="Immediate Actions" icon={Zap} defaultOpen>
                          <div className="space-y-1.5 mt-2">
                            {detail.rootCause.immediateActions.map((a: string, i: number) => (
                              <div key={i} className="flex items-start gap-2 text-xs">
                                <CheckCircle className="h-3 w-3 mt-0.5 text-success flex-shrink-0" />
                                <span>{a}</span>
                              </div>
                            ))}
                          </div>
                        </ExpandableSection>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Mitigation Checklist */}
                {checklist.length > 0 && (
                  <Card className="dashboard-card">
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckCircle className="h-4 w-4 text-success" />
                          <span className="text-base">Mitigation Checklist</span>
                        </div>
                        <span className="text-xs text-muted-foreground">{completedTasks}/{checklist.length}</span>
                      </CardTitle>
                      <div className="w-full bg-muted rounded-full h-1.5 mt-2">
                        <motion.div
                          className="bg-success h-1.5 rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${progressPercentage}%` }}
                        />
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {checklist.map(item => (
                          <div key={item.id} className="flex items-center space-x-3 py-1">
                            <Checkbox
                              checked={item.completed}
                              onCheckedChange={() => setChecklist(prev => prev.map(c => c.id === item.id ? { ...c, completed: !c.completed } : c))}
                            />
                            <span className={`text-sm ${item.completed ? "line-through text-muted-foreground" : ""}`}>
                              {item.task}
                            </span>
                          </div>
                        ))}
                      </div>
                      {completedTasks === checklist.length && checklist.length > 0 && (
                        <div className="mt-4">
                          <Button
                            onClick={() => { transitionStatus("resolved"); }}
                            className="w-full"
                            disabled={statusUpdating}
                          >
                            <CheckCircle className="h-4 w-4 mr-2" />
                            Mark Incident Resolved
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            </Tabs>
          </motion.div>
        </>
      )}
    </div>
  );
}
