import { useState } from "react";
import { motion } from "framer-motion";
import {
  Terminal,
  Upload,
  Sparkles,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  ShieldAlert,
  Activity,
  Cpu,
  Server,
  Clock,
  ChevronDown,
  ChevronRight,
  Loader2,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

const SAMPLE_LOG = `2026-05-16T08:14:22Z INFO  api-gateway   request id=req_8821 path=/v1/orders status=200 latency=132ms
2026-05-16T08:14:25Z WARN  auth-service  token verification slow user=u_4421 latency=1820ms
2026-05-16T08:14:27Z ERROR payments-svc  stripe.charge timeout after 30000ms order=ord_9912
2026-05-16T08:14:28Z ERROR payments-svc  retry exhausted (3/3) order=ord_9912
2026-05-16T08:14:30Z WARN  orders-db     connection pool 95% utilized (19/20)
2026-05-16T08:14:33Z ERROR auth-service  JWT signature invalid user=u_4421 ip=10.0.4.21
2026-05-16T08:14:35Z ERROR auth-service  JWT signature invalid user=u_4421 ip=10.0.4.21
2026-05-16T08:14:39Z ERROR orders-db     OOMKilled container=orders-db-7d pod=orders-db-7d-x9z
2026-05-16T08:14:41Z INFO  deploy-bot    rollout payments-svc revision=42 status=failed`;

interface Finding {
  id: string;
  title: string;
  severity: "critical" | "warning" | "info";
  service: string;
  count: number;
  rootCause: string;
  description: string;
  recommendations: string[];
}

const MOCK_FINDINGS: Finding[] = [
  {
    id: "f1",
    title: "Payments service timing out against Stripe",
    severity: "critical",
    service: "payments-svc",
    count: 4,
    rootCause: "Upstream Stripe API latency exceeding configured 30s timeout; retry budget exhausted.",
    description:
      "Multiple ERROR events show stripe.charge timing out followed by retry exhaustion. No successful charges in the captured window.",
    recommendations: [
      "Increase Stripe client timeout to 45s with exponential backoff",
      "Add circuit breaker around payments-svc → Stripe calls",
      "Page on-call if retry-exhausted rate > 1/min for 5m",
    ],
  },
  {
    id: "f2",
    title: "Repeated JWT signature failures",
    severity: "critical",
    service: "auth-service",
    count: 2,
    rootCause: "Same user/IP submitting invalid JWT signatures — likely key rotation drift or credential stuffing attempt.",
    description:
      "Two consecutive invalid signatures for user u_4421 from 10.0.4.21 within 8 seconds. Worth correlating with auth audit logs.",
    recommendations: [
      "Verify JWT signing key rotation propagated to all auth pods",
      "Add rate limit on invalid-signature events per IP",
      "Trigger security review for user u_4421",
    ],
  },
  {
    id: "f3",
    title: "Orders DB pod OOMKilled",
    severity: "critical",
    service: "orders-db",
    count: 1,
    rootCause: "Container memory limit exceeded under connection pool saturation.",
    description:
      "Connection pool at 95% utilization immediately preceded an OOMKill of the orders-db pod, indicating undersized memory limits or a query-side leak.",
    recommendations: [
      "Raise memory limit on orders-db deployment to 2Gi",
      "Profile long-running queries during the incident window",
      "Scale connection pool max to 40 and add pool saturation alert",
    ],
  },
  {
    id: "f4",
    title: "Auth service latency spike",
    severity: "warning",
    service: "auth-service",
    count: 1,
    rootCause: "Token verification crossed 1.8s — likely cold cache after deploy.",
    description:
      "Latency well above the 250ms p95 SLO. Single event, but worth tracking if it recurs after deploys.",
    recommendations: [
      "Warm JWKS cache on pod start",
      "Add SLO burn-rate alert on auth-service",
    ],
  },
  {
    id: "f5",
    title: "Failed rollout of payments-svc",
    severity: "warning",
    service: "deploy-bot",
    count: 1,
    rootCause: "Rollout revision 42 reported failed status — correlates with payment timeouts above.",
    description:
      "Deployment failure occurred during the same window as payment errors. Likely linked.",
    recommendations: [
      "Roll back payments-svc to revision 41",
      "Block deploys while error rate > 2%",
    ],
  },
];

const SUGGESTED_ACTIONS = [
  "Roll back payments-svc to last healthy revision",
  "Increase memory limit on orders-db pods to 2Gi",
  "Add circuit breaker for Stripe API calls",
  "Open security review for repeated JWT failures",
  "Notify on-call: payments + orders-db incidents correlated",
];

const severityStyles: Record<Finding["severity"], { badge: string; icon: typeof AlertTriangle; ring: string }> = {
  critical: {
    badge: "bg-destructive/10 text-destructive border-destructive/30",
    icon: AlertCircle,
    ring: "border-destructive/40",
  },
  warning: {
    badge: "bg-warning/10 text-warning border-warning/30",
    icon: AlertTriangle,
    ring: "border-warning/40",
  },
  info: {
    badge: "bg-primary/10 text-primary border-primary/30",
    icon: Info,
    ring: "border-primary/30",
  },
};

export function LogAnalyzer() {
  const [logs, setLogs] = useState("");
  const [analyzed, setAnalyzed] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [openFindings, setOpenFindings] = useState<Record<string, boolean>>({ f1: true });
  const [checked, setChecked] = useState<Record<number, boolean>>({});

  const runAnalysis = () => {
    if (!logs.trim()) return;
    setAnalyzing(true);
    setAnalyzed(false);
    setTimeout(() => {
      setAnalyzing(false);
      setAnalyzed(true);
    }, 1100);
  };

  const handleFile = async (file: File) => {
    const text = await file.text();
    setLogs(text);
  };

  const loadSample = () => setLogs(SAMPLE_LOG);

  const errorCount = MOCK_FINDINGS.filter((f) => f.severity === "critical").reduce((a, b) => a + b.count, 0);
  const warningCount = MOCK_FINDINGS.filter((f) => f.severity === "warning").reduce((a, b) => a + b.count, 0);
  const affectedServices = Array.from(new Set(MOCK_FINDINGS.map((f) => f.service)));

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-6 space-y-6 max-w-[1400px] mx-auto"
    >
      {/* Page header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium tracking-wide uppercase">
            <Cpu className="h-3.5 w-3.5" />
            Engineering Intelligence
          </div>
          <h1 className="text-3xl font-bold mt-1 flex items-center gap-3">
            <Terminal className="h-7 w-7 text-primary" />
            Log Analyzer
          </h1>
          <p className="text-muted-foreground mt-1 max-w-2xl">
            Paste or upload application logs. The AI agent extracts errors, clusters incidents,
            infers root cause, and proposes remediation steps.
          </p>
        </div>
        <Badge variant="outline" className="bg-success/10 text-success border-success/30">
          <Sparkles className="h-3 w-3 mr-1" /> AI Agent Online
        </Badge>
      </div>

      {/* Input area */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <CardTitle className="text-lg">Log Input</CardTitle>
              <CardDescription>Paste raw logs or upload a .log / .txt file.</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={loadSample}>
                Load sample
              </Button>
              <label>
                <input
                  type="file"
                  accept=".log,.txt,text/plain"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
                />
                <Button variant="outline" size="sm" asChild>
                  <span className="cursor-pointer">
                    <Upload className="h-4 w-4 mr-1.5" /> Upload
                  </span>
                </Button>
              </label>
              <Button size="sm" onClick={runAnalysis} disabled={!logs.trim() || analyzing}>
                {analyzing ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Analyzing
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-1.5" /> Run AI Analysis
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Textarea
            value={logs}
            onChange={(e) => setLogs(e.target.value)}
            placeholder="Paste logs here, e.g. application stdout, Kubernetes events, or CloudWatch exports…"
            className="font-mono text-xs min-h-[180px] bg-muted/30"
          />
        </CardContent>
      </Card>

      {analyzed && (
        <>
          {/* Metrics summary */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              label="Errors"
              value={errorCount}
              icon={AlertCircle}
              tone="destructive"
              hint="Critical events detected"
            />
            <MetricCard
              label="Warnings"
              value={warningCount}
              icon={AlertTriangle}
              tone="warning"
              hint="Non-fatal anomalies"
            />
            <MetricCard
              label="Affected services"
              value={affectedServices.length}
              icon={Server}
              tone="primary"
              hint={affectedServices.join(", ")}
            />
            <MetricCard
              label="Time window"
              value="19s"
              icon={Clock}
              tone="muted"
              hint="Span of captured events"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* AI Analysis Panel */}
            <div className="lg:col-span-2 space-y-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-primary" />
                    <CardTitle className="text-lg">AI Analysis Summary</CardTitle>
                  </div>
                  <CardDescription>Synthesis across {MOCK_FINDINGS.length} findings.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
                    A failed rollout of <span className="font-mono">payments-svc</span> is correlated with{" "}
                    repeated Stripe timeouts and exhausted retries. Simultaneously, the{" "}
                    <span className="font-mono">orders-db</span> pod was OOMKilled while its connection pool
                    saturated, and <span className="font-mono">auth-service</span> reported repeated invalid
                    JWT signatures from a single user/IP. Likely a deploy-induced incident with a parallel
                    suspicious auth pattern.
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="bg-destructive/10 text-destructive border-destructive/30">
                      Severity: Critical
                    </Badge>
                    <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">
                      Confidence: 86%
                    </Badge>
                    <Badge variant="outline">
                      <ShieldAlert className="h-3 w-3 mr-1" /> Possible security signal
                    </Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Key findings */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Key Findings</CardTitle>
                  <CardDescription>Grouped incidents detected in the log stream.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  {MOCK_FINDINGS.map((f) => {
                    const styles = severityStyles[f.severity];
                    const Icon = styles.icon;
                    const open = openFindings[f.id] ?? false;
                    return (
                      <Collapsible
                        key={f.id}
                        open={open}
                        onOpenChange={(v) => setOpenFindings((s) => ({ ...s, [f.id]: v }))}
                      >
                        <div className={cn("rounded-lg border bg-card", styles.ring)}>
                          <CollapsibleTrigger className="w-full flex items-start gap-3 p-4 text-left">
                            <Icon
                              className={cn(
                                "h-5 w-5 flex-shrink-0 mt-0.5",
                                f.severity === "critical" && "text-destructive",
                                f.severity === "warning" && "text-warning",
                                f.severity === "info" && "text-primary"
                              )}
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-medium text-sm">{f.title}</h3>
                                <Badge variant="outline" className={cn("text-[10px] py-0 h-5", styles.badge)}>
                                  {f.severity}
                                </Badge>
                                <Badge variant="outline" className="text-[10px] py-0 h-5">
                                  {f.service}
                                </Badge>
                                <span className="text-[11px] text-muted-foreground">×{f.count}</span>
                              </div>
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                                {f.description}
                              </p>
                            </div>
                            {open ? (
                              <ChevronDown className="h-4 w-4 text-muted-foreground mt-1" />
                            ) : (
                              <ChevronRight className="h-4 w-4 text-muted-foreground mt-1" />
                            )}
                          </CollapsibleTrigger>
                          <CollapsibleContent>
                            <div className="px-4 pb-4 pl-12 space-y-3 text-sm">
                              <div>
                                <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                                  Suspected root cause
                                </div>
                                <p>{f.rootCause}</p>
                              </div>
                              <div>
                                <div className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
                                  Recommended fixes
                                </div>
                                <ul className="list-disc pl-5 space-y-1">
                                  {f.recommendations.map((r, i) => (
                                    <li key={i}>{r}</li>
                                  ))}
                                </ul>
                              </div>
                            </div>
                          </CollapsibleContent>
                        </div>
                      </Collapsible>
                    );
                  })}
                </CardContent>
              </Card>
            </div>

            {/* Suggested actions */}
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5 text-success" />
                    Suggested Actions
                  </CardTitle>
                  <CardDescription>Triaged remediation checklist.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {SUGGESTED_ACTIONS.map((a, i) => (
                    <label
                      key={i}
                      className="flex items-start gap-3 p-2.5 rounded-md hover:bg-muted/50 cursor-pointer transition-colors"
                    >
                      <Checkbox
                        checked={!!checked[i]}
                        onCheckedChange={(v) =>
                          setChecked((s) => ({ ...s, [i]: Boolean(v) }))
                        }
                        className="mt-0.5"
                      />
                      <span
                        className={cn(
                          "text-sm leading-snug",
                          checked[i] && "line-through text-muted-foreground"
                        )}
                      >
                        {a}
                      </span>
                    </label>
                  ))}
                  <div className="pt-3 border-t mt-2">
                    <Progress
                      value={
                        (Object.values(checked).filter(Boolean).length / SUGGESTED_ACTIONS.length) * 100
                      }
                      className="h-1.5"
                    />
                    <p className="text-xs text-muted-foreground mt-2">
                      {Object.values(checked).filter(Boolean).length} of {SUGGESTED_ACTIONS.length} complete
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" /> Service Impact
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {affectedServices.map((s) => {
                    const count = MOCK_FINDINGS.filter((f) => f.service === s).reduce(
                      (a, b) => a + b.count,
                      0
                    );
                    return (
                      <div key={s} className="flex items-center justify-between text-sm">
                        <span className="font-mono">{s}</span>
                        <Badge variant="outline" className="bg-muted/40">
                          {count} event{count > 1 ? "s" : ""}
                        </Badge>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}

      {!analyzed && !analyzing && (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-muted-foreground">
            <Terminal className="h-10 w-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">Provide logs above, then run the AI analysis to see findings.</p>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}

function MetricCard({
  label,
  value,
  icon: Icon,
  tone,
  hint,
}: {
  label: string;
  value: string | number;
  icon: typeof AlertCircle;
  tone: "destructive" | "warning" | "primary" | "muted";
  hint?: string;
}) {
  const toneClass = {
    destructive: "text-destructive bg-destructive/10",
    warning: "text-warning bg-warning/10",
    primary: "text-primary bg-primary/10",
    muted: "text-muted-foreground bg-muted",
  }[tone];

  return (
    <Card>
      <CardContent className="p-4 flex items-start gap-3">
        <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center flex-shrink-0", toneClass)}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground font-medium">{label}</p>
          <p className="text-2xl font-bold leading-tight">{value}</p>
          {hint && <p className="text-[11px] text-muted-foreground truncate mt-0.5">{hint}</p>}
        </div>
      </CardContent>
    </Card>
  );
}