import { useState } from "react";
import { motion } from "framer-motion";
import {
  GitPullRequest,
  GitBranch,
  Sparkles,
  ShieldAlert,
  Zap,
  Wrench,
  ServerCog,
  FileCode2,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Info,
  Clock,
  ChevronLeft,
  Bot,
  User,
  Cpu,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type RiskLevel = "low" | "moderate" | "high";
type ReviewStatus = "pending" | "in-review" | "changes-requested" | "approved";

interface PullRequest {
  id: string;
  number: number;
  title: string;
  repo: string;
  author: string;
  branch: string;
  changedFiles: number;
  additions: number;
  deletions: number;
  risk: RiskLevel;
  riskScore: number; // 0-100
  confidence: number; // 0-100
  status: ReviewStatus;
  timestamp: string;
  summary: string;
  categories: {
    label: string;
    icon: typeof ShieldAlert;
    count: number;
    tone: "destructive" | "warning" | "primary" | "success";
  }[];
  findings: {
    id: string;
    title: string;
    severity: "critical" | "warning" | "info";
    file: string;
    line: number;
    category: string;
    description: string;
    suggestion: string;
  }[];
  improvements: string[];
  timeline: {
    id: string;
    actor: "ai" | "user";
    name: string;
    message: string;
    time: string;
  }[];
}

const PRS: PullRequest[] = [
  {
    id: "pr-842",
    number: 842,
    title: "feat(payments): add Stripe webhook handler for refunds",
    repo: "acme/payments-svc",
    author: "alice",
    branch: "feat/refund-webhook",
    changedFiles: 9,
    additions: 312,
    deletions: 41,
    risk: "high",
    riskScore: 82,
    confidence: 91,
    status: "changes-requested",
    timestamp: "12m ago",
    summary:
      "Adds a webhook endpoint to process Stripe refund events. Introduces a new auth path and persists events to the orders DB. The handler is missing signature verification and stores raw payload including PII.",
    categories: [
      { label: "Security", icon: ShieldAlert, count: 3, tone: "destructive" },
      { label: "Reliability", icon: AlertCircle, count: 2, tone: "warning" },
      { label: "Performance", icon: Zap, count: 1, tone: "warning" },
      { label: "Best Practices", icon: Wrench, count: 2, tone: "primary" },
    ],
    findings: [
      {
        id: "f1",
        title: "Hardcoded secret detected",
        severity: "critical",
        file: "src/webhooks/stripe.ts",
        line: 22,
        category: "Security",
        description:
          "Stripe webhook signing secret is embedded as a string literal. Should be loaded from environment / secret manager.",
        suggestion: "Replace with `process.env.STRIPE_WEBHOOK_SECRET` and rotate the exposed key.",
      },
      {
        id: "f2",
        title: "Missing webhook signature verification",
        severity: "critical",
        file: "src/webhooks/stripe.ts",
        line: 48,
        category: "Security",
        description:
          "Endpoint accepts any payload as a valid Stripe event. Allows spoofed refunds.",
        suggestion: "Call `stripe.webhooks.constructEvent(rawBody, sig, secret)` before processing.",
      },
      {
        id: "f3",
        title: "Missing retry handling on DB write",
        severity: "warning",
        file: "src/webhooks/stripe.ts",
        line: 71,
        category: "Reliability",
        description:
          "Transient DB errors will drop the webhook event with no replay path.",
        suggestion: "Wrap with retry + dead-letter queue and return 5xx so Stripe redelivers.",
      },
      {
        id: "f4",
        title: "N+1 query loading refund items",
        severity: "warning",
        file: "src/services/refunds.ts",
        line: 104,
        category: "Performance",
        description: "Each refund triggers a per-item lookup inside a loop.",
        suggestion: "Batch with a single `IN (...)` query or `Promise.all`.",
      },
      {
        id: "f5",
        title: "Raw payload persisted with PII",
        severity: "warning",
        file: "src/webhooks/stripe.ts",
        line: 89,
        category: "Security",
        description: "Full Stripe event including email and last4 stored in `webhook_events.raw`.",
        suggestion: "Strip PII fields before persisting or encrypt the column.",
      },
    ],
    improvements: [
      "Extract webhook handler into a separate module for testability",
      "Add integration test that posts a signed Stripe event fixture",
      "Document refund handling in /docs/payments.md",
    ],
    timeline: [
      {
        id: "t1",
        actor: "ai",
        name: "Review Agent",
        message: "Initial review complete — 5 findings across 3 categories.",
        time: "12m ago",
      },
      {
        id: "t2",
        actor: "ai",
        name: "Review Agent",
        message: "Flagged 2 critical security issues. Blocking deploy until resolved.",
        time: "12m ago",
      },
      {
        id: "t3",
        actor: "user",
        name: "alice",
        message: "Will fix the signature check, pushing a follow-up commit.",
        time: "8m ago",
      },
    ],
  },
  {
    id: "pr-839",
    number: 839,
    title: "infra(terraform): widen RDS security group ingress",
    repo: "acme/infra",
    author: "bob",
    branch: "infra/rds-sg",
    changedFiles: 2,
    additions: 18,
    deletions: 4,
    risk: "high",
    riskScore: 74,
    confidence: 88,
    status: "in-review",
    timestamp: "34m ago",
    summary:
      "Opens RDS ingress to 0.0.0.0/0 on port 5432. This effectively exposes the production database to the public internet.",
    categories: [
      { label: "Infrastructure Risk", icon: ServerCog, count: 1, tone: "destructive" },
      { label: "Security", icon: ShieldAlert, count: 1, tone: "destructive" },
    ],
    findings: [
      {
        id: "f1",
        title: "Risky Terraform change: public DB exposure",
        severity: "critical",
        file: "infra/rds/main.tf",
        line: 41,
        category: "Infrastructure Risk",
        description:
          "ingress cidr_blocks set to [\"0.0.0.0/0\"] for tcp/5432 on production RDS instance.",
        suggestion:
          "Restrict to the VPC CIDR or a bastion security group. Require explicit override for any public exposure.",
      },
    ],
    improvements: [
      "Add tfsec / checkov to CI",
      "Require infra PRs to attach a risk justification",
    ],
    timeline: [
      {
        id: "t1",
        actor: "ai",
        name: "Review Agent",
        message: "Detected production blast-radius change. Marked High Risk.",
        time: "34m ago",
      },
    ],
  },
  {
    id: "pr-836",
    number: 836,
    title: "fix(api): handle null user in /v1/profile",
    repo: "acme/api-gateway",
    author: "carol",
    branch: "fix/profile-null",
    changedFiles: 1,
    additions: 6,
    deletions: 2,
    risk: "low",
    riskScore: 14,
    confidence: 96,
    status: "approved",
    timestamp: "1h ago",
    summary:
      "Adds a null guard on the user lookup in the profile route. Small, well-tested change with no security or infra impact.",
    categories: [
      { label: "Reliability", icon: CheckCircle2, count: 1, tone: "success" },
    ],
    findings: [
      {
        id: "f1",
        title: "Missing null handling fixed",
        severity: "info",
        file: "src/routes/profile.ts",
        line: 18,
        category: "Reliability",
        description: "Previously dereferenced user without checking presence.",
        suggestion: "Approved — change is minimal and covered by new test.",
      },
    ],
    improvements: ["Backfill similar null guards in /v1/orders"],
    timeline: [
      {
        id: "t1",
        actor: "ai",
        name: "Review Agent",
        message: "Low risk. Approved with one minor follow-up suggestion.",
        time: "1h ago",
      },
      {
        id: "t2",
        actor: "user",
        name: "carol",
        message: "Thanks — will open a follow-up PR for /v1/orders.",
        time: "55m ago",
      },
    ],
  },
  {
    id: "pr-831",
    number: 831,
    title: "chore(deps): bump lodash 4.17.20 → 4.17.21",
    repo: "acme/web",
    author: "dependabot",
    branch: "deps/lodash",
    changedFiles: 2,
    additions: 2,
    deletions: 2,
    risk: "moderate",
    riskScore: 38,
    confidence: 82,
    status: "pending",
    timestamp: "2h ago",
    summary:
      "Patch-level dependency bump. No code changes. Lockfile updated. Worth running full e2e before merging due to broad import surface.",
    categories: [
      { label: "Best Practices", icon: Wrench, count: 1, tone: "primary" },
    ],
    findings: [
      {
        id: "f1",
        title: "Run full e2e suite before merge",
        severity: "info",
        file: "package-lock.json",
        line: 1,
        category: "Best Practices",
        description: "Dependency is imported across 38 modules.",
        suggestion: "Trigger nightly e2e or require manual run on this PR.",
      },
    ],
    improvements: ["Auto-merge patch bumps after green CI"],
    timeline: [
      {
        id: "t1",
        actor: "ai",
        name: "Review Agent",
        message: "Patch bump, no breaking changes in changelog. Moderate due to import surface.",
        time: "2h ago",
      },
    ],
  },
];

const riskMeta: Record<RiskLevel, { label: string; tone: string; bar: string }> = {
  low: { label: "Low Risk", tone: "bg-success/10 text-success border-success/30", bar: "bg-success" },
  moderate: { label: "Moderate Risk", tone: "bg-warning/10 text-warning border-warning/30", bar: "bg-warning" },
  high: { label: "High Risk", tone: "bg-destructive/10 text-destructive border-destructive/30", bar: "bg-destructive" },
};

const statusMeta: Record<ReviewStatus, { label: string; tone: string }> = {
  pending: { label: "Pending", tone: "bg-muted text-muted-foreground" },
  "in-review": { label: "In Review", tone: "bg-primary/10 text-primary border-primary/30" },
  "changes-requested": {
    label: "Changes Requested",
    tone: "bg-destructive/10 text-destructive border-destructive/30",
  },
  approved: { label: "Approved", tone: "bg-success/10 text-success border-success/30" },
};

export function PRReviewer() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = PRS.find((p) => p.id === selectedId) ?? null;

  if (selected) {
    return <PRDetail pr={selected} onBack={() => setSelectedId(null)} />;
  }

  const highRisk = PRS.filter((p) => p.risk === "high").length;
  const blocking = PRS.filter((p) => p.status === "changes-requested").length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-6 space-y-6 max-w-[1400px] mx-auto"
    >
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium tracking-wide uppercase">
            <Cpu className="h-3.5 w-3.5" />
            Engineering Intelligence
          </div>
          <h1 className="text-3xl font-bold mt-1 flex items-center gap-3">
            <GitPullRequest className="h-7 w-7 text-primary" />
            PR Reviewer
          </h1>
          <p className="text-muted-foreground mt-1 max-w-2xl">
            Open pull requests targeting <span className="font-mono">main</span> are continuously
            reviewed by the AI agent for security, reliability, and infrastructure risk.
          </p>
        </div>
        <Badge variant="outline" className="bg-success/10 text-success border-success/30">
          <Sparkles className="h-3 w-3 mr-1" /> Auto-review enabled
        </Badge>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard label="Open PRs" value={PRS.length} icon={GitPullRequest} tone="primary" />
        <SummaryCard label="High risk" value={highRisk} icon={ShieldAlert} tone="destructive" />
        <SummaryCard label="Changes requested" value={blocking} icon={AlertTriangle} tone="warning" />
        <SummaryCard
          label="Approved"
          value={PRS.filter((p) => p.status === "approved").length}
          icon={CheckCircle2}
          tone="success"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Detected Pull Requests</CardTitle>
          <CardDescription>Targeting <span className="font-mono">main</span> across monitored repositories.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pull Request</TableHead>
                <TableHead>Repository</TableHead>
                <TableHead>Author</TableHead>
                <TableHead>Branch</TableHead>
                <TableHead className="text-right">Files</TableHead>
                <TableHead>Risk</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PRS.map((pr) => (
                <TableRow
                  key={pr.id}
                  className="cursor-pointer"
                  onClick={() => setSelectedId(pr.id)}
                >
                  <TableCell>
                    <div className="font-medium text-sm">{pr.title}</div>
                    <div className="text-xs text-muted-foreground">#{pr.number}</div>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{pr.repo}</TableCell>
                  <TableCell className="text-sm">{pr.author}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 text-xs font-mono">
                      <GitBranch className="h-3 w-3" />
                      {pr.branch}
                      <span className="text-muted-foreground mx-1">→</span>
                      <span>main</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right text-sm">{pr.changedFiles}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 min-w-[140px]">
                      <Badge variant="outline" className={cn("text-[10px]", riskMeta[pr.risk].tone)}>
                        {riskMeta[pr.risk].label}
                      </Badge>
                      <div className="w-16">
                        <Progress value={pr.riskScore} className="h-1.5" />
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("text-[10px]", statusMeta[pr.status].tone)}>
                      {statusMeta[pr.status].label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3" /> {pr.timestamp}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </motion.div>
  );
}

function PRDetail({ pr, onBack }: { pr: PullRequest; onBack: () => void }) {
  const severityIcon = {
    critical: <AlertCircle className="h-4 w-4 text-destructive" />,
    warning: <AlertTriangle className="h-4 w-4 text-warning" />,
    info: <Info className="h-4 w-4 text-primary" />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="p-6 space-y-6 max-w-[1400px] mx-auto"
    >
      <div>
        <Button variant="ghost" size="sm" onClick={onBack} className="mb-3 -ml-2">
          <ChevronLeft className="h-4 w-4 mr-1" /> Back to PRs
        </Button>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="text-xs text-muted-foreground font-mono">
              {pr.repo} · #{pr.number}
            </div>
            <h1 className="text-2xl font-bold mt-1 flex items-center gap-2">
              <GitPullRequest className="h-6 w-6 text-primary" />
              {pr.title}
            </h1>
            <div className="flex items-center gap-2 mt-2 text-sm text-muted-foreground flex-wrap">
              <span>{pr.author}</span>
              <span>·</span>
              <span className="flex items-center gap-1 font-mono text-xs">
                <GitBranch className="h-3 w-3" /> {pr.branch} → main
              </span>
              <span>·</span>
              <span>
                {pr.changedFiles} files <span className="text-success">+{pr.additions}</span>{" "}
                <span className="text-destructive">-{pr.deletions}</span>
              </span>
              <span>·</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" /> {pr.timestamp}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={cn(statusMeta[pr.status].tone)}>
              {statusMeta[pr.status].label}
            </Badge>
            <Badge variant="outline" className={cn(riskMeta[pr.risk].tone)}>
              {riskMeta[pr.risk].label}
            </Badge>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {/* AI Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-primary" /> AI Review Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed">{pr.summary}</p>
            </CardContent>
          </Card>

          {/* Categories */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Review Categories</CardTitle>
              <CardDescription>Findings grouped by concern.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {pr.categories.map((c) => {
                  const tone = {
                    destructive: "bg-destructive/10 text-destructive border-destructive/30",
                    warning: "bg-warning/10 text-warning border-warning/30",
                    primary: "bg-primary/10 text-primary border-primary/30",
                    success: "bg-success/10 text-success border-success/30",
                  }[c.tone];
                  const Icon = c.icon;
                  return (
                    <div
                      key={c.label}
                      className={cn(
                        "rounded-lg border p-3 flex items-center gap-3",
                        tone
                      )}
                    >
                      <Icon className="h-5 w-5" />
                      <div>
                        <div className="text-xs uppercase tracking-wide opacity-80">{c.label}</div>
                        <div className="font-bold text-lg leading-tight">{c.count}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* Findings */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Highlighted Findings</CardTitle>
              <CardDescription>Inline issues detected by the AI reviewer.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {pr.findings.map((f) => (
                <div key={f.id} className="rounded-lg border p-4 bg-card">
                  <div className="flex items-start gap-3">
                    {severityIcon[f.severity]}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-medium text-sm">{f.title}</h3>
                        <Badge variant="outline" className="text-[10px]">
                          {f.category}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground font-mono mt-1">
                        <FileCode2 className="h-3 w-3" />
                        {f.file}:{f.line}
                      </div>
                      <p className="text-sm mt-2">{f.description}</p>
                      <div className="mt-2 rounded-md bg-muted/40 border-l-2 border-primary px-3 py-2 text-xs">
                        <span className="font-semibold text-primary">Suggestion:</span> {f.suggestion}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Improvements */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Wrench className="h-5 w-5 text-primary" /> Suggested Improvements
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-2">
                {pr.improvements.map((i, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 text-success mt-0.5 flex-shrink-0" />
                    <span>{i}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          {/* Risk assessment */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-primary" /> AI Risk Assessment
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Risk score</span>
                  <span className="font-semibold">{pr.riskScore}/100</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className={cn("h-full transition-all", riskMeta[pr.risk].bar)}
                    style={{ width: `${pr.riskScore}%` }}
                  />
                </div>
                <Badge variant="outline" className={cn("mt-2 text-[10px]", riskMeta[pr.risk].tone)}>
                  {riskMeta[pr.risk].label}
                </Badge>
              </div>
              <div>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-muted-foreground">Confidence</span>
                  <span className="font-semibold">{pr.confidence}%</span>
                </div>
                <Progress value={pr.confidence} className="h-1.5" />
              </div>
              <div className="rounded-md border bg-muted/30 p-3 text-xs">
                <div className="font-semibold mb-1">Deployment impact</div>
                <p className="text-muted-foreground leading-relaxed">
                  {pr.risk === "high"
                    ? "Blocks deploy. Affects production-critical path."
                    : pr.risk === "moderate"
                    ? "Allow deploy with extra CI gate."
                    : "Safe to deploy with standard checks."}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Timeline */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Review Timeline</CardTitle>
              <CardDescription>Agent activity and comments.</CardDescription>
            </CardHeader>
            <CardContent>
              <ol className="relative border-l border-border pl-5 space-y-4">
                {pr.timeline.map((t) => (
                  <li key={t.id} className="relative">
                    <span
                      className={cn(
                        "absolute -left-[27px] top-0 h-5 w-5 rounded-full flex items-center justify-center",
                        t.actor === "ai"
                          ? "bg-primary/10 text-primary border border-primary/30"
                          : "bg-muted text-muted-foreground border"
                      )}
                    >
                      {t.actor === "ai" ? <Bot className="h-3 w-3" /> : <User className="h-3 w-3" />}
                    </span>
                    <div className="text-xs flex items-center gap-2">
                      <span className="font-semibold">{t.name}</span>
                      <span className="text-muted-foreground">{t.time}</span>
                    </div>
                    <p className="text-sm mt-1">{t.message}</p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
      </div>
    </motion.div>
  );
}

function SummaryCard({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string | number;
  icon: typeof GitPullRequest;
  tone: "primary" | "destructive" | "warning" | "success";
}) {
  const toneClass = {
    primary: "text-primary bg-primary/10",
    destructive: "text-destructive bg-destructive/10",
    warning: "text-warning bg-warning/10",
    success: "text-success bg-success/10",
  }[tone];
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className={cn("h-10 w-10 rounded-lg flex items-center justify-center", toneClass)}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground font-medium">{label}</p>
          <p className="text-2xl font-bold leading-tight">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}