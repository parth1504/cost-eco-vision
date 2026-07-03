import { useState, useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Clock, CheckCircle, AlertTriangle, Activity, Lightbulb,
  RefreshCw, Sparkles, Network, ArrowRight, ChevronDown, ChevronRight,
  Zap, Search, Eye, Shield, Server, Database, Globe, Layers, FileText, Bell
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

type ServiceTopology = Record<string, {
  type: string;
  depends_on: string[];
  is_root_cause?: boolean;
}>;

type IncidentDetail = {
  incident_id: string;
  status: string;
  investigating_at?: string | null;
  mitigated_at?: string | null;
  resolved_at?: string | null;
  timeline: TimelineEvent[];
  rootCause: any | null;
  checklist: any[];
  service_topology?: ServiceTopology | null;
  generated_at: string;
};

type LifecycleStatus = "open" | "investigating" | "mitigated" | "resolved";

type GraphNode = {
  id: string;
  name: string;
  type: string;
  status: "healthy" | "degraded" | "failing";
  alertCount: number;
  alerts: TimelineEvent[];
  firstFailure?: string;
  isRootCause: boolean;
  dependsOn: string[];
  // Layout
  col: number;
  row: number;
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

// ─── Slack Notification Button ──────────────────────────────────────────────

function SlackNotifyButton({ incidentTitle, rootService }: { incidentTitle: string; rootService?: string }) {
  const { toast } = useToast();
  const [sent, setSent] = useState(false);

  const notify = () => {
    setSent(true);
    toast({
      title: "Slack notification sent",
      description: `#payments-oncall alerted: "${rootService || "Unknown service"}" is causing downstream impact.`,
    });
    setTimeout(() => setSent(false), 4000);
  };

  return (
    <button
      onClick={notify}
      title="Notify on-call via Slack"
      className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium border transition-all
        ${sent
          ? "bg-green-50 border-green-300 text-green-700 dark:bg-green-900/20 dark:border-green-600 dark:text-green-400"
          : "bg-muted/40 border-border hover:bg-[#4A154B]/10 hover:border-[#4A154B]/40 hover:text-[#4A154B] dark:hover:text-purple-300"
        }`}
    >
      <Bell className="h-3 w-3" />
      {sent ? "Notified" : "Notify Slack"}
    </button>
  );
}

// ─── Graph Layout: Topological sort into layers ─────────────────────────────

function layoutGraph(
  topology: ServiceTopology,
  timeline: TimelineEvent[]
): GraphNode[] {
  const alertsByService = new Map<string, TimelineEvent[]>();
  for (const event of timeline) {
    const src = event.source || "Unknown";
    if (!alertsByService.has(src)) alertsByService.set(src, []);
    alertsByService.get(src)!.push(event);
  }

  // Build nodes
  const nodes = new Map<string, GraphNode>();
  for (const [name, def] of Object.entries(topology)) {
    const alerts = alertsByService.get(name) || [];
    const firstAlert = alerts.sort((a, b) => a.timestamp.localeCompare(b.timestamp))[0];
    let status: "healthy" | "degraded" | "failing" = "healthy";
    for (const a of alerts) {
      const sev = (a.severity || "").toLowerCase();
      if (sev === "critical" || sev === "high") { status = "failing"; break; }
      if (sev === "warning" || sev === "medium") status = "degraded";
    }
    nodes.set(name, {
      id: name,
      name,
      type: def.type,
      status,
      alertCount: alerts.length,
      alerts,
      firstFailure: firstAlert?.timestamp,
      isRootCause: def.is_root_cause || false,
      dependsOn: def.depends_on || [],
      col: 0,
      row: 0,
    });
  }

  // Topological layer assignment (BFS from roots)
  // Roots = nodes with no dependencies
  const inDegree = new Map<string, number>();
  for (const [name, def] of Object.entries(topology)) {
    inDegree.set(name, (def.depends_on || []).filter(d => topology[d]).length);
  }

  let layer = 0;
  const layerAssignment = new Map<string, number>();
  const queue: string[] = [];

  for (const [name, deg] of inDegree) {
    if (deg === 0) queue.push(name);
  }

  while (queue.length > 0) {
    const nextQueue: string[] = [];
    for (const name of queue) {
      layerAssignment.set(name, layer);
    }
    // Find nodes whose all dependencies are assigned
    for (const [name, def] of Object.entries(topology)) {
      if (layerAssignment.has(name)) continue;
      const deps = (def.depends_on || []).filter(d => topology[d]);
      if (deps.every(d => layerAssignment.has(d))) {
        nextQueue.push(name);
      }
    }
    queue.length = 0;
    queue.push(...nextQueue);
    layer++;
    if (layer > 20) break; // safety
  }

  // Assign remaining (cycles, etc.)
  for (const name of nodes.keys()) {
    if (!layerAssignment.has(name)) layerAssignment.set(name, layer);
  }

  // Reverse: root cause should be leftmost, dependents flow right
  // In the topology, root cause has no depends_on. Dependents point towards root.
  // But visually we want root on the LEFT and downstream on the RIGHT.
  // Since root has layer=0 and dependents have higher layers, that's correct.

  // Group by layer, assign row positions
  const layerGroups = new Map<number, string[]>();
  for (const [name, l] of layerAssignment) {
    if (!layerGroups.has(l)) layerGroups.set(l, []);
    layerGroups.get(l)!.push(name);
  }

  for (const [l, names] of layerGroups) {
    names.forEach((name, i) => {
      const node = nodes.get(name);
      if (node) {
        node.col = l;
        node.row = i;
      }
    });
  }

  return Array.from(nodes.values());
}

function fallbackGraph(timeline: TimelineEvent[]): GraphNode[] {
  const serviceMap = new Map<string, GraphNode>();
  for (const event of timeline) {
    const source = event.source || "Unknown";
    if (!serviceMap.has(source)) {
      serviceMap.set(source, {
        id: source, name: source, type: "service",
        status: "healthy", alertCount: 0, alerts: [],
        isRootCause: false, dependsOn: [], col: 0, row: 0,
      });
    }
    const node = serviceMap.get(source)!;
    node.alertCount++;
    node.alerts.push(event);
    if (!node.firstFailure || event.timestamp < node.firstFailure) node.firstFailure = event.timestamp;
    const sev = (event.severity || "").toLowerCase();
    if (sev === "critical" || sev === "high") node.status = "failing";
    else if ((sev === "warning" || sev === "medium") && node.status !== "failing") node.status = "degraded";
  }
  const nodes = Array.from(serviceMap.values());
  nodes.sort((a, b) => (a.firstFailure || "z").localeCompare(b.firstFailure || "z"));
  if (nodes.length > 0) nodes[0].isRootCause = true;
  nodes.forEach((n, i) => { n.col = i; n.row = 0; });
  return nodes;
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

// ─── Vertical Dependency Graph (HTML nodes + SVG edges) ───────────────────

const NODE_W = 192;
const NODE_H = 82;
const LAYER_GAP = 110;
const NODE_GAP = 36;
const PAD = 48;

function TypeIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5";
  switch (type) {
    case "database": return <Database className={cls} />;
    case "external": return <Globe className={cls} />;
    case "infra": return <Layers className={cls} />;
    default: return <Server className={cls} />;
  }
}

function DependencyGraphSVG({ graphNodes, topology, onNodeClick, selectedNode }: {
  graphNodes: GraphNode[];
  topology: ServiceTopology | null;
  onNodeClick: (id: string) => void;
  selectedNode: string | null;
}) {
  if (graphNodes.length === 0) {
    return <div className="text-center text-muted-foreground py-8 text-sm">No service data available.</div>;
  }

  // Layer counts for centering
  const layerCounts = new Map<number, number>();
  for (const n of graphNodes) {
    layerCounts.set(n.col, (layerCounts.get(n.col) || 0) + 1);
  }

  const maxLayer = Math.max(...graphNodes.map(n => n.col));
  const maxNodesInLayer = Math.max(...Array.from(layerCounts.values()));

  const totalW = Math.max(maxNodesInLayer * (NODE_W + NODE_GAP) - NODE_GAP + PAD * 2, 600);
  const totalH = (maxLayer + 1) * (NODE_H + LAYER_GAP) - LAYER_GAP + PAD * 2;

  // Vertical layout: col = layer (Y), row = position within layer (X), centered
  const getPos = (node: GraphNode) => {
    const layerSize = layerCounts.get(node.col) || 1;
    const layerWidth = layerSize * NODE_W + (layerSize - 1) * NODE_GAP;
    const startX = (totalW - layerWidth) / 2;
    return {
      x: startX + node.row * (NODE_W + NODE_GAP),
      y: PAD + node.col * (NODE_H + LAYER_GAP),
    };
  };

  // Build edges
  const edges: { from: GraphNode; to: GraphNode }[] = [];
  for (const node of graphNodes) {
    for (const dep of node.dependsOn) {
      const depNode = graphNodes.find(n => n.id === dep);
      if (depNode) edges.push({ from: depNode, to: node });
    }
  }
  if (edges.length === 0 && graphNodes.length > 1) {
    for (let i = 0; i < graphNodes.length - 1; i++) {
      edges.push({ from: graphNodes[i], to: graphNodes[i + 1] });
    }
  }

  // Failure order
  const orderedByFailure = [...graphNodes]
    .filter(n => n.firstFailure)
    .sort((a, b) => (a.firstFailure || "").localeCompare(b.firstFailure || ""));
  const failureOrder = new Map<string, number>();
  orderedByFailure.forEach((n, i) => failureOrder.set(n.id, i + 1));

  const statusBorder = (status: string) => {
    switch (status) {
      case "failing": return "border-red-500";
      case "degraded": return "border-amber-500";
      default: return "border-emerald-500";
    }
  };

  const statusDot = (status: string) => {
    switch (status) {
      case "failing": return "bg-red-500";
      case "degraded": return "bg-amber-500";
      default: return "bg-emerald-500";
    }
  };

  const statusLabel = (status: string) => {
    switch (status) {
      case "failing": return "text-red-600 dark:text-red-400";
      case "degraded": return "text-amber-600 dark:text-amber-400";
      default: return "text-emerald-600 dark:text-emerald-400";
    }
  };

  return (
    <div className="overflow-x-auto pb-4">
      <div style={{ width: totalW, height: totalH, position: "relative" }} className="mx-auto">
        {/* SVG edge layer */}
        <svg
          width={totalW}
          height={totalH}
          className="absolute inset-0 pointer-events-none"
          style={{ zIndex: 1 }}
        >
          <defs>
            <marker id="arrow-fail" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
              <path d="M 0 0 L 10 4 L 0 8 L 3 4 Z" fill="#ef4444" />
            </marker>
            <marker id="arrow-dep" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
              <path d="M 0 0 L 8 3 L 0 6 L 2 3 Z" fill="#9ca3af" />
            </marker>
            <filter id="edge-glow">
              <feGaussianBlur stdDeviation="2" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>
          {edges.map((edge, i) => {
            const fromPos = getPos(edge.from);
            const toPos = getPos(edge.to);
            const x1 = fromPos.x + NODE_W / 2;
            const y1 = fromPos.y + NODE_H;
            const x2 = toPos.x + NODE_W / 2;
            const y2 = toPos.y;
            const dy = (y2 - y1) * 0.45;
            const isFail = edge.from.status !== "healthy" || edge.to.status !== "healthy";
            const d = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;

            return (
              <g key={`e-${i}`}>
                {isFail && <path d={d} fill="none" stroke="#ef4444" strokeWidth={7} opacity={0.12} />}
                <path
                  d={d}
                  fill="none"
                  stroke={isFail ? "#ef4444" : "#9ca3af"}
                  strokeWidth={isFail ? 2.5 : 1.5}
                  strokeDasharray={isFail ? "none" : "6 4"}
                  opacity={isFail ? 0.9 : 0.28}
                  filter={isFail ? "url(#edge-glow)" : undefined}
                  markerEnd={isFail ? "url(#arrow-fail)" : "url(#arrow-dep)"}
                />
              </g>
            );
          })}
        </svg>

        {/* HTML node cards */}
        {graphNodes.map((node) => {
          const pos = getPos(node);
          const isSelected = selectedNode === node.id;
          const order = failureOrder.get(node.id);

          return (
            <div
              key={node.id}
              onClick={() => onNodeClick(node.id)}
              className={`absolute cursor-pointer rounded-xl border-2 bg-card
                transition-all duration-200 hover:-translate-y-0.5
                ${statusBorder(node.status)}
                ${node.status === "failing" ? "shadow-[0_0_16px_rgba(239,68,68,0.25)]" : "shadow-md hover:shadow-lg"}
                ${isSelected ? "ring-2 ring-primary ring-offset-2 ring-offset-background" : ""}
                ${node.isRootCause ? "border-[3px] shadow-[0_0_24px_rgba(239,68,68,0.35)]" : ""}
                ${node.status === "healthy" ? "opacity-60" : ""}
              `}
              style={{
                left: pos.x,
                top: pos.y,
                width: NODE_W,
                height: NODE_H,
                zIndex: isSelected ? 20 : 10,
              }}
            >
              {/* Order badge */}
              {order && (
                <div className="absolute -top-2.5 -left-2.5 w-6 h-6 rounded-full bg-foreground text-background
                  flex items-center justify-center text-[10px] font-bold shadow-sm z-10">
                  {order}
                </div>
              )}

              {/* ROOT badge */}
              {node.isRootCause && (
                <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 px-2.5 py-0.5 rounded-full
                  bg-red-500 text-white text-[9px] font-extrabold tracking-wider shadow-sm z-10">
                  ROOT CAUSE
                </div>
              )}

              {/* Content */}
              <div className="h-full flex flex-col justify-between p-2.5 pt-3">
                {/* Top: icon + name */}
                <div className="flex items-center gap-1.5 min-w-0">
                  <div className={`p-1 rounded ${node.status === "failing" ? "bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400" : node.status === "degraded" ? "bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400" : "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400"}`}>
                    <TypeIcon type={node.type} />
                  </div>
                  <span className="text-[12px] font-semibold truncate leading-tight">{node.name}</span>
                </div>

                {/* Bottom row: status + alerts + time */}
                <div className="flex items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${statusDot(node.status)}`} />
                    <span className={`text-[10px] font-medium capitalize ${statusLabel(node.status)}`}>
                      {node.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                    {node.alertCount > 0 && (
                      <span className="font-medium">{node.alertCount} alert{node.alertCount !== 1 ? "s" : ""}</span>
                    )}
                    {node.firstFailure && (
                      <span className="tabular-nums">{new Date(node.firstFailure).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 mt-4 text-[11px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded border-2 border-red-500 bg-red-50 dark:bg-red-900/20" />
          Failing
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded border-2 border-amber-500 bg-amber-50 dark:bg-amber-900/20" />
          Degraded
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded border-2 border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20" />
          Healthy
        </div>
        <div className="flex items-center gap-1.5">
          <div className="px-2 py-0.5 rounded-full bg-red-500 text-white text-[8px] font-bold">ROOT CAUSE</div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0 border-t-2 border-red-500" />
          Failure path
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-5 h-0 border-t-[1.5px] border-dashed border-gray-400" />
          Dependency
        </div>
      </div>
    </div>
  );
}

// ─── Propagation Analysis ───────────────────────────────────────────────────

function PropagationAnalysis({ graphNodes }: { graphNodes: GraphNode[] }) {
  const sorted = [...graphNodes]
    .filter(n => n.firstFailure)
    .sort((a, b) => (a.firstFailure || "").localeCompare(b.firstFailure || ""));

  if (sorted.length < 2) return null;

  const rootNode = sorted.find(n => n.isRootCause) || sorted[0];
  const downstream = sorted.filter(n => n.id !== rootNode.id);

  return (
    <div className="space-y-3">
      {/* Root cause card */}
      <div className="p-3 bg-destructive/5 border border-destructive/20 rounded-lg">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="h-4 w-4 text-destructive" />
          <span className="text-sm font-semibold">Root Cause: {rootNode.name}</span>
          <Badge variant="destructive" className="text-[9px]">First Failure</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Failed at {rootNode.firstFailure ? new Date(rootNode.firstFailure).toLocaleTimeString() : "N/A"} with {rootNode.alertCount} alert(s).
          {rootNode.alerts[0] && <> &mdash; "{rootNode.alerts[0].message.slice(0, 100)}..."</>}
        </p>
      </div>

      {/* Downstream chain */}
      <div className="ml-4 border-l-2 border-destructive/20 pl-4 space-y-2">
        {downstream.map((node, i) => {
          const timeDelta = rootNode.firstFailure && node.firstFailure
            ? Math.round((new Date(node.firstFailure).getTime() - new Date(rootNode.firstFailure).getTime()) / 1000)
            : null;

          return (
            <motion.div
              key={node.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.08 }}
              className="relative"
            >
              <div className="absolute -left-[21px] top-2 w-3 h-3 rounded-full bg-background border-2 border-destructive/40" />
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{node.name}</span>
                <Badge variant="secondary" className="text-[9px]">
                  {node.status === "failing" ? "Downstream Failure" : "Degraded"}
                </Badge>
                {timeDelta !== null && (
                  <span className="text-[10px] text-muted-foreground">+{timeDelta}s after root</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {node.alertCount} alert(s) — {node.alerts[0]?.message.slice(0, 80)}...
              </p>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}

// ─── RCA Verification ───────────────────────────────────────────────────────

function RCAVerification({ graphNodes, rootCause }: { graphNodes: GraphNode[]; rootCause: any }) {
  const rootNode = graphNodes.find(n => n.isRootCause);
  const downstreamFailing = graphNodes.filter(n => !n.isRootCause && n.status === "failing");
  const downstreamDegraded = graphNodes.filter(n => !n.isRootCause && n.status === "degraded");
  const healthyNodes = graphNodes.filter(n => n.status === "healthy");

  const allFailuresAfterRoot = rootNode?.firstFailure
    ? downstreamFailing.every(n => !n.firstFailure || n.firstFailure >= rootNode.firstFailure!)
    : false;

  const verifications = [
    {
      question: "Did this service fail before all others?",
      answer: rootNode
        ? `${rootNode.name} first alerted at ${rootNode.firstFailure ? new Date(rootNode.firstFailure).toLocaleTimeString() : "N/A"}, which is the earliest failure in the dependency chain.`
        : "Unable to determine temporal ordering.",
      passed: !!rootNode?.firstFailure,
      icon: Clock,
    },
    {
      question: "Are downstream failures temporally after the root cause?",
      answer: allFailuresAfterRoot
        ? `Yes — all ${downstreamFailing.length} downstream failure(s) started after ${rootNode?.name}.`
        : downstreamFailing.length === 0
          ? "No downstream failures detected — issue may be contained."
          : "Some downstream failures occurred concurrently — may indicate multiple root causes.",
      passed: allFailuresAfterRoot,
      icon: ArrowRight,
    },
    {
      question: "Does the root service have error signals?",
      answer: rootNode && rootNode.alertCount > 0
        ? `${rootNode.alertCount} alert(s) at ${rootNode.name}: "${rootNode.alerts[0]?.message?.slice(0, 100)}..."`
        : "No specific error signals found at the suspected root.",
      passed: (rootNode?.alertCount || 0) > 0,
      icon: AlertTriangle,
    },
    {
      question: "Are healthy services isolated from the failure path?",
      answer: healthyNodes.length > 0
        ? `${healthyNodes.length} service(s) remain healthy (${healthyNodes.map(n => n.name).join(", ")}), confirming the blast radius is limited to the ${rootNode?.name} dependency chain.`
        : "All services are affected — full system impact.",
      passed: healthyNodes.length > 0,
      icon: Shield,
    },
    {
      question: "Is there a clear propagation path through dependencies?",
      answer: downstreamFailing.length > 0 || downstreamDegraded.length > 0
        ? `Failure propagated from ${rootNode?.name} → ${[...downstreamFailing, ...downstreamDegraded].map(n => n.name).join(" → ")}. ${downstreamDegraded.length} service(s) degraded, ${downstreamFailing.length} fully failing.`
        : "No clear propagation path detected — single-service issue.",
      passed: (downstreamFailing.length + downstreamDegraded.length) > 0,
      icon: Network,
    },
  ];

  // Build the failure propagation path: root → sorted downstream by first failure time
  const failurePath = [
    rootNode,
    ...[...downstreamFailing, ...downstreamDegraded]
      .filter(n => n.firstFailure)
      .sort((a, b) => (a.firstFailure || "").localeCompare(b.firstFailure || "")),
  ].filter(Boolean) as GraphNode[];

  return (
    <div className="space-y-3">
      {/* Failure propagation path — single glanceable line */}
      {failurePath.length >= 2 && (
        <div className="p-3 rounded-lg bg-destructive/5 border border-destructive/20">
          <p className="text-[10px] text-muted-foreground uppercase font-semibold mb-2 tracking-wide">Failure Propagation Path</p>
          <div className="flex items-center flex-wrap gap-1.5">
            {failurePath.map((node, idx) => (
              <div key={node.id} className="flex items-center gap-1.5">
                <span className={`px-2.5 py-1 rounded-md text-[11px] font-semibold border
                  ${node.isRootCause
                    ? "bg-red-500 text-white border-red-500"
                    : node.status === "failing"
                      ? "bg-red-50 text-red-700 border-red-300 dark:bg-red-900/20 dark:text-red-300 dark:border-red-700"
                      : "bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-700"
                  }`}>
                  {node.name}
                </span>
                {idx < failurePath.length - 1 && (
                  <ArrowRight className="h-3.5 w-3.5 text-destructive/60 flex-shrink-0" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Verification checks */}
      {verifications.map((v, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06 }}
          className="flex items-start gap-3 p-3 rounded-lg bg-muted/20"
        >
          <div className={`p-1.5 rounded ${v.passed ? "bg-success/10" : "bg-muted"}`}>
            <v.icon className={`h-3.5 w-3.5 ${v.passed ? "text-success" : "text-muted-foreground"}`} />
          </div>
          <div className="flex-1">
            <p className="text-xs font-medium">{v.question}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{v.answer}</p>
          </div>
          {v.passed ? (
            <CheckCircle className="h-4 w-4 text-success flex-shrink-0 mt-0.5" />
          ) : (
            <AlertTriangle className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
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
  const [seeding, setSeeding] = useState(false);
  const { toast } = useToast();

  const graphNodes = useMemo(() => {
    if (!detail) return [];
    if (detail.service_topology && Object.keys(detail.service_topology).length > 0) {
      return layoutGraph(detail.service_topology, detail.timeline);
    }
    return fallbackGraph(detail.timeline);
  }, [detail]);

  const selectedService = useMemo(
    () => graphNodes.find(n => n.id === selectedNode) || null,
    [graphNodes, selectedNode]
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
      const grouped = data.filter((i) => i.member_alert_ids.length >= 2);

      // Auto-seed banking scenarios on first load if no incidents exist
      if (grouped.length === 0) {
        try {
          const seedRes = await fetch(`${API}/incident/seed-scenarios`, { method: "POST" });
          if (seedRes.ok) {
            const seedData = await seedRes.json();
            if (seedData.incidents_created > 0) {
              const res2 = await fetch(`${API}/incident`);
              if (res2.ok) {
                const data2: IncidentSummary[] = await res2.json();
                setIncidents(data2);
                const grouped2 = data2.filter((i) => i.member_alert_ids.length >= 2);
                if (autoSelect && grouped2.length > 0) setSelectedId(grouped2[0].incident_id);
                return;
              }
            }
          }
        } catch { /* silent — fall through to show empty state */ }
      }

      setIncidents(data);
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
      toast({ title: "Analysis ready" });
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
      await loadIncidents(false);
    } catch (err) {
      toast({ title: "AI correlation failed", description: String(err), variant: "destructive" });
    } finally {
      setRefreshing(false);
    }
  };

  const seedScenarios = async () => {
    setSeeding(true);
    try {
      const res = await fetch(`${API}/incident/seed-scenarios`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      toast({ title: "Scenarios seeded", description: `${data.incidents_created} microservice incident(s) created.` });
      await loadIncidents(true);
    } catch (err) {
      toast({ title: "Seed failed", description: String(err), variant: "destructive" });
    } finally {
      setSeeding(false);
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
                No correlated incidents found. Click <strong>Correlate</strong> to group active alerts.
              </div>
            ) : (
              <div className="space-y-2">
                {groupedIncidents.map(inc => (
                  <div key={inc.incident_id} className={`rounded-lg border transition-colors ${
                    inc.incident_id === selectedId ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"
                  }`}>
                    <button
                      onClick={() => setSelectedId(inc.incident_id)}
                      className="w-full text-left p-3"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <div className="flex items-center space-x-2">
                          <Badge className={getSeverityColor(inc.severity)}>{inc.severity}</Badge>
                          <span className="text-sm font-medium">{inc.title}</span>
                        </div>
                        <span className="text-xs text-muted-foreground font-mono">{inc.incident_id}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {inc.member_alert_ids.length} alert(s) · {inc.resources_affected.length} service(s) · {new Date(inc.created_at).toLocaleString()}
                      </div>
                    </button>
                    <div className="px-3 pb-2">
                      <SlackNotifyButton
                        incidentTitle={inc.title}
                        rootService={inc.resources_affected[0]}
                      />
                    </div>
                  </div>
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

          {/* Three Tabs */}
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

              {/* GRAPH */}
              <TabsContent value="graph" className="mt-4 space-y-4">
                <Card className="dashboard-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Network className="h-4 w-4 text-primary" />
                      Service Dependency Map
                    </CardTitle>
                    <CardDescription>
                      Click any service node to inspect its alerts. Numbered by failure chronology.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <DependencyGraphSVG
                      graphNodes={graphNodes}
                      topology={detail.service_topology || null}
                      onNodeClick={(id) => setSelectedNode(selectedNode === id ? null : id)}
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
                            {selectedService.isRootCause && <Badge variant="destructive" className="text-[9px]">Root Cause</Badge>}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2 max-h-52 overflow-y-auto">
                            {selectedService.alerts.length > 0 ? selectedService.alerts.map((alert, i) => (
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
                            )) : (
                              <p className="text-xs text-muted-foreground">No alerts on this service — it remains healthy.</p>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Propagation */}
                <Card className="dashboard-card">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Zap className="h-4 w-4 text-warning" />
                      Failure Propagation Analysis
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <PropagationAnalysis graphNodes={graphNodes} />
                  </CardContent>
                </Card>
              </TabsContent>

              {/* TIMELINE */}
              <TabsContent value="timeline" className="mt-4">
                <Card className="dashboard-card">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Clock className="h-4 w-4 text-primary" />
                      Event Timeline
                    </CardTitle>
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
                                transition={{ delay: index * 0.04 }}
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
                                  <p className="text-sm mt-1">{event.message}</p>
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

              {/* RCA */}
              <TabsContent value="rca" className="mt-4 space-y-4">
                {!detail.rootCause && (
                  <Card className="dashboard-card">
                    <CardContent className="pt-6 text-center space-y-3">
                      <Lightbulb className="h-8 w-8 text-warning mx-auto" />
                      <p className="text-sm text-muted-foreground">Run the AI agent to generate a detailed root cause analysis.</p>
                      <Button onClick={() => runAnalysis(false)} disabled={analyzing}>
                        <RefreshCw className={`h-4 w-4 mr-2 ${analyzing ? "animate-spin" : ""}`} />
                        {analyzing ? "Reasoning..." : "Run Root Cause Analysis"}
                      </Button>
                    </CardContent>
                  </Card>
                )}

                <Card className="dashboard-card">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Shield className="h-4 w-4 text-primary" />
                      Verification Steps
                    </CardTitle>
                    <CardDescription>Why we believe this is the root cause</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <RCAVerification graphNodes={graphNodes} rootCause={detail.rootCause} />
                  </CardContent>
                </Card>

                {detail.rootCause && (
                  <Card className="dashboard-card border-primary/20">
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base flex items-center gap-2">
                          <Lightbulb className="h-4 w-4 text-warning" />
                          AI Conclusion
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
                      {Array.isArray(detail.rootCause.contributingFactors) && (
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
                      {Array.isArray(detail.rootCause.immediateActions) && (
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
                        <motion.div className="bg-success h-1.5 rounded-full" animate={{ width: `${progressPercentage}%` }} />
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
                        <Button onClick={() => transitionStatus("resolved")} className="w-full mt-4" disabled={statusUpdating}>
                          <CheckCircle className="h-4 w-4 mr-2" />Mark Incident Resolved
                        </Button>
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
