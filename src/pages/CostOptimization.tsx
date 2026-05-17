import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { DollarSign, TrendingUp, Leaf, Zap, Settings, Sparkles, Eye, Code, ShieldCheck, ShieldAlert, Shield, HelpCircle, ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import confetti from 'canvas-confetti';
import { CostSentinel } from "@/components/advanced/CostSentinel";
import { Badge } from "@/components/ui/badge";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function CostOptimization() {
  const [idleResourcesEnabled, setIdleResourcesEnabled] = useState(true);
  const [rightSizingLevel, setRightSizingLevel] = useState([70]);
  const [schedulingEnabled, setSchedulingEnabled] = useState(false);
  const [autoScalingLevel, setAutoScalingLevel] = useState([50]);
  const [storageOptEnabled, setStorageOptEnabled] = useState(true);
  const [projectedSavings, setProjectedSavings] = useState({ monthly: 0, yearly: 0, co2: 0, optimization_score: 0 });
  const [sections, setSections] = useState<any>({});
  const [implementationPlan, setImplementationPlan] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [simulation, setSimulation] = useState<any>(null);
  const [viewMode, setViewMode] = useState<"executive" | "developer">("executive");
  const [explainOpen, setExplainOpen] = useState<{ right_sizing: boolean; auto_scaling: boolean }>({ right_sizing: false, auto_scaling: false });
  const [explanations, setExplanations] = useState<any>({});
  const [explainLoading, setExplainLoading] = useState<{ right_sizing: boolean; auto_scaling: boolean }>({ right_sizing: false, auto_scaling: false });

  const { toast } = useToast();

  useEffect(() => {
    fetchOptimizationData();
  }, []);

  useEffect(() => {
    updateProjections();
  }, [idleResourcesEnabled, rightSizingLevel, schedulingEnabled, autoScalingLevel, storageOptEnabled]);

  const fetchOptimizationData = async () => {
    try {
      console.log("🔄 Attempting to fetch optimization data from backend...");
      const response = await fetch("http://localhost:8000/optimization", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      });
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Successfully fetched optimization data from backend");

      if (data.config) {
        setIdleResourcesEnabled(data.config.idle_resources_enabled);
        setRightSizingLevel([data.config.right_sizing_level]);
        setSchedulingEnabled(data.config.scheduling_enabled);
        setAutoScalingLevel([data.config.auto_scaling_level]);
        setStorageOptEnabled(data.config.storage_optimization_enabled);
      }

      if (data.projections) {
        setProjectedSavings(data.projections);
      }
      if (data.sections) {
        setSections(data.sections);
      }
      if (data.implementation_plan) {
        setImplementationPlan(data.implementation_plan);
      }
    } catch (error) {
      console.error("❌ Failed to fetch from backend:", error);
      console.log("📦 Using default configuration as fallback");
      
      // Use current state values and calculate savings locally
      const calculateLocalSavings = () => {
        let monthlySavings = 0;
        let co2Reduction = 0;

        if (idleResourcesEnabled) {
          monthlySavings += 2;
          co2Reduction += 0.8;
        }

        monthlySavings += (rightSizingLevel[0] / 100) * 4;
        co2Reduction += (rightSizingLevel[0] / 100) * 1.2;

        if (schedulingEnabled) {
          monthlySavings += 156;
          co2Reduction += 0.5;
        }

        monthlySavings += (autoScalingLevel[0] / 100) * 3;
        co2Reduction += (autoScalingLevel[0] / 100) * 0.9;

        if (storageOptEnabled) {
          monthlySavings += 89;
          co2Reduction += 0.3;
        }

        return {
          monthly: Math.round(monthlySavings),
          yearly: Math.round(monthlySavings * 12),
          co2: Math.round(co2Reduction * 10) / 10,
          optimization_score: Math.min(95, Math.round((monthlySavings / 1190) * 2))
        };
      };
      
      setProjectedSavings(calculateLocalSavings());
      
      toast({
        title: "Backend Unavailable",
        description: "Restart server to fetch live alerts",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

  const updateProjections = async () => {
    try {
      const config = {
        idle_resources_enabled: idleResourcesEnabled,
        right_sizing_level: rightSizingLevel[0],
        scheduling_enabled: schedulingEnabled,
        auto_scaling_level: autoScalingLevel[0],
        storage_optimization_enabled: storageOptEnabled
      };

      const response = await fetch("http://localhost:8000/optimization/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config })
      });

      const data = await response.json();
      if (data.projections) {
        setProjectedSavings(data.projections);
      }
      if (data.sections) {
        setSections(data.sections);
      }
      if (data.implementation_plan) {
        setImplementationPlan(data.implementation_plan);
      }
    } catch (error) {
      console.error("Failed to update projections:", error);
    }
  };

  const fetchSimulation = useCallback(async () => {
    try {
      const response = await fetch("http://localhost:8000/optimization/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          right_sizing_level: rightSizingLevel[0],
          auto_scaling_level: autoScalingLevel[0],
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setSimulation(data);
      }
    } catch (error) {
      console.error("Simulation fetch failed:", error);
    }
  }, [rightSizingLevel, autoScalingLevel]);

  useEffect(() => {
    fetchSimulation();
  }, [fetchSimulation]);

  const fetchExplanation = async (section: "right_sizing" | "auto_scaling") => {
    if (explanations[section] && !explainLoading[section]) {
      setExplainOpen((prev) => ({ ...prev, [section]: !prev[section] }));
      return;
    }
    setExplainLoading((prev) => ({ ...prev, [section]: true }));
    setExplainOpen((prev) => ({ ...prev, [section]: true }));
    try {
      const response = await fetch("http://localhost:8000/optimization/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          section,
          config: {
            right_sizing_level: rightSizingLevel[0],
            auto_scaling_level: autoScalingLevel[0],
          },
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setExplanations((prev: any) => ({ ...prev, [section]: data }));
      }
    } catch (error) {
      console.error(`Explainability fetch failed for ${section}:`, error);
    } finally {
      setExplainLoading((prev) => ({ ...prev, [section]: false }));
    }
  };

  const handleApplyOptimization = async () => {
    try {
      // Save current configuration to backend
      await updateProjections();

      // Trigger confetti animation
      confetti({
        particleCount: 100,
        spread: 70,
        origin: { y: 0.6 }
      });

      toast({
        title: "🎉 Optimization Plan Applied!",
        description: `Your plan will save $${projectedSavings.monthly}/month and reduce CO₂ by ${projectedSavings.co2} kgs annually.`,
      });
    } catch (error) {
      console.error("Failed to apply optimization:", error);
      toast({
        title: "Error",
        description: "Failed to apply optimization plan",
        variant: "destructive"
      });
    }
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* Header */}
      <motion.div variants={itemVariants}>
        <h1 className="text-3xl font-bold text-foreground">Cost Optimization</h1>
        <p className="text-muted-foreground mt-2">
          Configure AI-powered optimization settings to maximize your cloud savings
        </p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Configuration Panel */}
        <motion.div variants={itemVariants} className="lg:col-span-2 space-y-6">
          {/* Idle Resources */}
          <Card className="dashboard-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-warning/10 rounded-lg">
                    <Zap className="h-5 w-5 text-warning" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Idle Resource Management</CardTitle>
                    <CardDescription>
                      Automatically identify and stop underutilized resources
                    </CardDescription>
                  </div>
                </div>
                <Switch
                  checked={idleResourcesEnabled}
                  onCheckedChange={setIdleResourcesEnabled}
                />
              </div>
            </CardHeader>
            {idleResourcesEnabled && (
              <CardContent className="pt-0">
                <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                  <p className="text-sm text-success font-medium">
                    {sections.idle_resources?.affected_resources > 0
                      ? `✓ Potential monthly savings: $${sections.idle_resources?.estimated_savings || 27}`
                      : "✓ No idle resources detected"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {sections.idle_resources?.affected_resources ?? 0} idle instance(s) identified for optimization
                  </p>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Right-sizing */}
          <Card className="dashboard-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    <Settings className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Resource Right-sizing</CardTitle>
                    <CardDescription>
                      Optimize instance sizes based on actual usage patterns
                    </CardDescription>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant={viewMode === "executive" ? "default" : "ghost"}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setViewMode("executive")}
                  >
                    <Eye className="h-3 w-3 mr-1" />Exec
                  </Button>
                  <Button
                    variant={viewMode === "developer" ? "default" : "ghost"}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setViewMode("developer")}
                  >
                    <Code className="h-3 w-3 mr-1" />Dev
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <Label htmlFor="rightsizing">Optimization Level</Label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{rightSizingLevel[0]}%</span>
                    {simulation?.right_sizing?.risk_zone && (
                      <Badge variant={
                        simulation.right_sizing.risk_zone === "safe" ? "default" :
                        simulation.right_sizing.risk_zone === "moderate" ? "secondary" : "destructive"
                      } className="text-[10px] px-1.5 py-0">
                        {simulation.right_sizing.risk_zone === "safe" && <ShieldCheck className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.right_sizing.risk_zone === "moderate" && <Shield className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.right_sizing.risk_zone === "risky" && <ShieldAlert className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.right_sizing.risk_zone}
                      </Badge>
                    )}
                  </div>
                </div>
                <Slider
                  id="rightsizing"
                  min={0}
                  max={100}
                  step={10}
                  value={rightSizingLevel}
                  onValueChange={setRightSizingLevel}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>Conservative</span>
                  {simulation?.right_sizing?.safe_operating_range && (
                    <span className="text-success">Safe zone: 0–{simulation.right_sizing.safe_operating_range.max}%</span>
                  )}
                  <span>Aggressive</span>
                </div>
              </div>

              {/* Executive View */}
              {viewMode === "executive" && simulation?.right_sizing?.executive && (
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-primary font-medium">
                      Savings: ${simulation.right_sizing.executive.cost_savings_monthly}/month
                      <span className="text-muted-foreground ml-1 font-normal">
                        ({simulation.right_sizing.capacity_reduction_pct}% capacity reduction)
                      </span>
                    </p>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span>Risk: <span className={
                      simulation.right_sizing.executive.risk_level === "safe" ? "text-success font-medium" :
                      simulation.right_sizing.executive.risk_level === "moderate" ? "text-warning font-medium" : "text-destructive font-medium"
                    }>{simulation.right_sizing.executive.risk_level}</span></span>
                    <span className="text-muted-foreground">|</span>
                    <span>Stability: <span className={
                      simulation.right_sizing.risk_zone === "safe" ? "text-success font-medium" :
                      simulation.right_sizing.risk_zone === "moderate" ? "text-warning font-medium" : "text-destructive font-medium"
                    }>{simulation.right_sizing.risk_zone}</span></span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {simulation.right_sizing.executive.recommendation}
                  </p>
                </div>
              )}

              {/* Developer View */}
              {viewMode === "developer" && simulation?.right_sizing?.developer && (
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-muted-foreground">Latency impact:</span>
                      <span className="ml-1 font-medium">+{simulation.right_sizing.developer.latency_increase_pct}%</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Error rate:</span>
                      <span className="ml-1 font-medium">+{simulation.right_sizing.developer.error_rate_increase_pct}%</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Retry amplification:</span>
                      <span className="ml-1 font-medium">{simulation.right_sizing.developer.retry_amplification_factor}x</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Replicas affected:</span>
                      <span className="ml-1 font-medium">{simulation.right_sizing.developer.replicas_affected}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Capacity reduction:</span>
                      <span className="ml-1 font-medium">{simulation.right_sizing.developer.capacity_reduction_pct}%</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Debug complexity:</span>
                      <span className="ml-1 font-medium">{simulation.right_sizing.developer.debugging_complexity}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Fallback when no simulation data */}
              {!simulation?.right_sizing && (
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                  <p className="text-sm text-primary font-medium">
                    Projected savings: ${sections.right_sizing?.estimated_savings || 34}/month
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {sections.right_sizing?.candidates ?? 0} resource(s) can be right-sized
                  </p>
                </div>
              )}

              {/* Explainability */}
              <button
                onClick={() => fetchExplanation("right_sizing")}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <HelpCircle className="h-3.5 w-3.5" />
                <span>Why this recommendation?</span>
                {explainOpen.right_sizing ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>

              {explainOpen.right_sizing && (
                <div className="p-3 bg-muted/30 border border-border rounded-lg space-y-3 text-xs animate-in slide-in-from-top-2">
                  {explainLoading.right_sizing ? (
                    <p className="text-muted-foreground italic">Generating explanation...</p>
                  ) : explanations.right_sizing ? (
                    <>
                      <div>
                        <p className="font-medium text-foreground mb-1">Reasoning</p>
                        <p className="text-muted-foreground">{explanations.right_sizing.reasoning}</p>
                      </div>
                      <div>
                        <p className="font-medium text-foreground mb-1">Evidence</p>
                        <div className="space-y-1">
                          {explanations.right_sizing.evidence?.map((e: any, i: number) => (
                            <div key={i} className="flex items-start gap-1.5">
                              <Badge variant={e.severity === "critical" ? "destructive" : e.severity === "warning" ? "secondary" : "default"} className="text-[9px] px-1 py-0 mt-0.5">{e.severity}</Badge>
                              <span>{e.description}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="font-medium text-foreground mb-1">Assumptions</p>
                        <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                          {explanations.right_sizing.assumptions?.map((a: string, i: number) => (
                            <li key={i}>{a}</li>
                          ))}
                        </ul>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Scheduling */}
          <Card className="dashboard-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-eco/10 rounded-lg">
                    <TrendingUp className="h-5 w-5 text-eco" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Smart Scheduling</CardTitle>
                    <CardDescription>
                      Automatically start/stop resources based on usage patterns
                    </CardDescription>
                  </div>
                </div>
                <Switch
                  checked={schedulingEnabled}
                  onCheckedChange={setSchedulingEnabled}
                />
              </div>
            </CardHeader>
            {schedulingEnabled && (
              <CardContent className="pt-0">
                <div className="space-y-3">
                  <div className="p-4 bg-eco/5 border border-eco/20 rounded-lg">
                    <p className="text-sm text-eco font-medium">
                      ✓ {sections.scheduling?.schedulable_resources > 0
                        ? `${sections.scheduling.schedulable_resources} dev/test resource(s) can be scheduled off-hours`
                        : "No schedulable dev/test resources detected"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Estimated savings: ${sections.scheduling?.estimated_savings || 18}/month
                    </p>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Auto-scaling */}
          <Card className="dashboard-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-success/10 rounded-lg">
                    <Sparkles className="h-5 w-5 text-success" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Auto-scaling Optimization</CardTitle>
                    <CardDescription>
                      Fine-tune auto-scaling policies for better cost efficiency
                    </CardDescription>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    variant={viewMode === "executive" ? "default" : "ghost"}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setViewMode("executive")}
                  >
                    <Eye className="h-3 w-3 mr-1" />Exec
                  </Button>
                  <Button
                    variant={viewMode === "developer" ? "default" : "ghost"}
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => setViewMode("developer")}
                  >
                    <Code className="h-3 w-3 mr-1" />Dev
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <Label htmlFor="autoscaling">Scaling Sensitivity</Label>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{autoScalingLevel[0]}</span>
                    {simulation?.auto_scaling?.risk_zone && (
                      <Badge variant={
                        simulation.auto_scaling.risk_zone === "safe" ? "default" :
                        simulation.auto_scaling.risk_zone === "moderate" ? "secondary" : "destructive"
                      } className="text-[10px] px-1.5 py-0">
                        {simulation.auto_scaling.risk_zone === "safe" && <ShieldCheck className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.auto_scaling.risk_zone === "moderate" && <Shield className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.auto_scaling.risk_zone === "risky" && <ShieldAlert className="h-2.5 w-2.5 mr-0.5" />}
                        {simulation.auto_scaling.risk_zone}
                      </Badge>
                    )}
                  </div>
                </div>
                <Slider
                  id="autoscaling"
                  min={0}
                  max={10}
                  step={1}
                  value={autoScalingLevel}
                  onValueChange={setAutoScalingLevel}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>Stable</span>
                  {simulation?.auto_scaling?.safe_operating_range && (
                    <span className="text-success">Safe zone: 0–{simulation.auto_scaling.safe_operating_range.max}</span>
                  )}
                  <span>Aggressive</span>
                </div>
              </div>

              {/* Executive View */}
              {viewMode === "executive" && simulation?.auto_scaling?.executive && (
                <div className="p-4 bg-success/5 border border-success/20 rounded-lg space-y-2">
                  <div className="flex items-center justify-between">
                    <p className="text-sm text-success font-medium">
                      Net savings: ${simulation.auto_scaling.executive.cost_savings_monthly}/month
                    </p>
                    <span className="text-xs text-muted-foreground">
                      Waste reclaimed: ${simulation.auto_scaling.executive.over_provisioning_waste}/mo
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span>Risk: <span className={
                      simulation.auto_scaling.executive.risk_level === "safe" ? "text-success font-medium" :
                      simulation.auto_scaling.executive.risk_level === "moderate" ? "text-warning font-medium" : "text-destructive font-medium"
                    }>{simulation.auto_scaling.executive.risk_level}</span></span>
                    <span className="text-muted-foreground">|</span>
                    <span>Stability: <span className={
                      simulation.auto_scaling.risk_zone === "safe" ? "text-success font-medium" :
                      simulation.auto_scaling.risk_zone === "moderate" ? "text-warning font-medium" : "text-destructive font-medium"
                    }>{simulation.auto_scaling.risk_zone}</span></span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {simulation.auto_scaling.executive.recommendation}
                  </p>
                </div>
              )}

              {/* Developer View */}
              {viewMode === "developer" && simulation?.auto_scaling?.developer && (
                <div className="p-4 bg-success/5 border border-success/20 rounded-lg space-y-2">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-muted-foreground">Scale events/day:</span>
                      <span className="ml-1 font-medium">{simulation.auto_scaling.developer.scaling_events_per_day}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Response time:</span>
                      <span className="ml-1 font-medium">{simulation.auto_scaling.developer.response_time_sec}s</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Stability score:</span>
                      <span className="ml-1 font-medium">{simulation.auto_scaling.developer.stability_score}/10</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Spike latency:</span>
                      <span className="ml-1 font-medium">+{simulation.auto_scaling.developer.spike_latency_increase_pct}%</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Retry factor:</span>
                      <span className="ml-1 font-medium">{simulation.auto_scaling.developer.retry_during_scaling_factor}x</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Debug complexity:</span>
                      <span className="ml-1 font-medium">{simulation.auto_scaling.developer.debugging_complexity}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Fallback when no simulation data */}
              {!simulation?.auto_scaling && (
                <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                  <p className="text-sm text-success font-medium">
                    Projected savings: ${sections.auto_scaling?.estimated_savings || 22}/month
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reducing {sections.auto_scaling?.waste_reduction_pct || 12}% over-provisioning waste
                  </p>
                </div>
              )}

              {/* Explainability */}
              <button
                onClick={() => fetchExplanation("auto_scaling")}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                <HelpCircle className="h-3.5 w-3.5" />
                <span>Why this recommendation?</span>
                {explainOpen.auto_scaling ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              </button>

              {explainOpen.auto_scaling && (
                <div className="p-3 bg-muted/30 border border-border rounded-lg space-y-3 text-xs animate-in slide-in-from-top-2">
                  {explainLoading.auto_scaling ? (
                    <p className="text-muted-foreground italic">Generating explanation...</p>
                  ) : explanations.auto_scaling ? (
                    <>
                      <div>
                        <p className="font-medium text-foreground mb-1">Reasoning</p>
                        <p className="text-muted-foreground">{explanations.auto_scaling.reasoning}</p>
                      </div>
                      <div>
                        <p className="font-medium text-foreground mb-1">Evidence</p>
                        <div className="space-y-1">
                          {explanations.auto_scaling.evidence?.map((e: any, i: number) => (
                            <div key={i} className="flex items-start gap-1.5">
                              <Badge variant={e.severity === "critical" ? "destructive" : e.severity === "warning" ? "secondary" : "default"} className="text-[9px] px-1 py-0 mt-0.5">{e.severity}</Badge>
                              <span>{e.description}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="font-medium text-foreground mb-1">Assumptions</p>
                        <ul className="list-disc list-inside text-muted-foreground space-y-0.5">
                          {explanations.auto_scaling.assumptions?.map((a: string, i: number) => (
                            <li key={i}>{a}</li>
                          ))}
                        </ul>
                      </div>
                    </>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Storage Optimization */}
          <Card className="dashboard-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    <DollarSign className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Storage Optimization</CardTitle>
                    <CardDescription>
                      Optimize storage classes and lifecycle policies
                    </CardDescription>
                  </div>
                </div>
                <Switch
                  checked={storageOptEnabled}
                  onCheckedChange={setStorageOptEnabled}
                />
              </div>
            </CardHeader>
            {storageOptEnabled && (
              <CardContent className="pt-0">
                <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                  <p className="text-sm text-primary font-medium">
                    ✓ {sections.storage?.candidates > 0
                      ? `${sections.storage.candidates} storage resource(s) can be optimized with lifecycle policies`
                      : "No storage optimization opportunities detected"}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Estimated savings: ${sections.storage?.estimated_savings || 8}/month
                  </p>
                </div>
              </CardContent>
            )}
          </Card>
        </motion.div>

        {/* Savings Projection Panel */}
        <motion.div variants={itemVariants} className="space-y-6">
          {/* Current Projections */}
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <DollarSign className="h-5 w-5 text-success" />
                <span>Projected Savings</span>
              </CardTitle>
              <CardDescription>Based on your current configuration</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="text-center">
                <div className="text-3xl font-bold text-success">
                  ${projectedSavings.monthly}
                </div>
                <p className="text-sm text-muted-foreground">per month</p>
              </div>

              <div className="text-center">
                <div className="text-2xl font-bold text-primary">
                  ${projectedSavings.yearly}
                </div>
                <p className="text-sm text-muted-foreground">per year</p>
              </div>

              <div className="text-center">
                <div className="text-xl font-bold text-eco flex items-center justify-center space-x-2">
                  <Leaf className="h-5 w-5" />
                  <span>{projectedSavings.co2} kgs</span>
                </div>
                <p className="text-sm text-muted-foreground">CO₂ reduction/year</p>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Optimization Score</span>
                  <span className="font-medium">{projectedSavings.optimization_score}%</span>
                </div>
                <Progress value={projectedSavings.optimization_score} className="h-3" />
              </div>
            </CardContent>
          </Card>

          {/* Implementation Timeline */}
          <Card className="dashboard-card">
            <CardHeader>
              <CardTitle className="text-base">Implementation Plan</CardTitle>
              <CardDescription>Estimated rollout timeline</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                {implementationPlan.length > 0 ? (
                  implementationPlan.map((phase, idx) => {
                    const dotColor = idx === 0 ? "bg-success" : idx === 1 ? "bg-primary" : "bg-muted-foreground";
                    return (
                      <div key={idx} className="flex items-center space-x-3">
                        <div className={`h-2 w-2 ${dotColor} rounded-full`} />
                        <div className="flex-1">
                          <p className="text-sm font-medium">{phase.title} ({phase.timeframe})</p>
                          <p className="text-xs text-muted-foreground">{phase.description}</p>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <>
                    <div className="flex items-center space-x-3">
                      <div className="h-2 w-2 bg-success rounded-full" />
                      <div className="flex-1">
                        <p className="text-sm font-medium">Immediate (0-1 days)</p>
                        <p className="text-xs text-muted-foreground">Idle resource cleanup</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-3">
                      <div className="h-2 w-2 bg-primary rounded-full" />
                      <div className="flex-1">
                        <p className="text-sm font-medium">Short-term (1-7 days)</p>
                        <p className="text-xs text-muted-foreground">Right-sizing & scheduling</p>
                      </div>
                    </div>
                    <div className="flex items-center space-x-3">
                      <div className="h-2 w-2 bg-muted-foreground rounded-full" />
                      <div className="flex-1">
                        <p className="text-sm font-medium">Long-term (1-4 weeks)</p>
                        <p className="text-xs text-muted-foreground">Auto-scaling optimization</p>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Apply Button */}
          <Button 
            onClick={handleApplyOptimization}
            className="w-full h-12 text-base font-medium action-success"
          >
            <Sparkles className="h-5 w-5 mr-2" />
            Apply Optimization Plan
          </Button>
        </motion.div>
      </div>

      {/* Advanced AI Features */}
      <CostSentinel />
    </motion.div>
  );
}