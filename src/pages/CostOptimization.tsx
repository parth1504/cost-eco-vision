import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { DollarSign, TrendingUp, Leaf, Zap, Settings, Sparkles } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import confetti from 'canvas-confetti';
import { CostSentinel } from "@/components/advanced/CostSentinel";
import { CapacityOracle } from "@/components/advanced/CapacityOracle";

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
  const [loading, setLoading] = useState(true);
  
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
    } catch (error) {
      console.error("Failed to update projections:", error);
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
        description: `Your plan will save $${projectedSavings.monthly}/month and reduce CO₂ by ${projectedSavings.co2} tons annually.`,
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
                    ✓ Potential monthly savings: $18
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    3 idle instances identified for optimization
                  </p>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Right-sizing */}
          <Card className="dashboard-card">
            <CardHeader>
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
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <Label htmlFor="rightsizing">Optimization Level</Label>
                  <span className="text-sm font-medium">{rightSizingLevel[0]}%</span>
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
                  <span>Aggressive</span>
                </div>
              </div>
              <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <p className="text-sm text-primary font-medium">
                  Projected savings: ${Math.round((rightSizingLevel[0] / 100) * 4)}/month
                </p>
              </div>
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
                      ✓ Schedule detected: Stop dev/test resources 6 PM - 8 AM
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Estimated savings: $156/month
                    </p>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Auto-scaling */}
          <Card className="dashboard-card">
            <CardHeader>
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
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex justify-between mb-2">
                  <Label htmlFor="autoscaling">Scaling Sensitivity</Label>
                  <span className="text-sm font-medium">{autoScalingLevel[0]}%</span>
                </div>
                <Slider
                  id="autoscaling"
                  min={0}
                  max={100}
                  step={10}
                  value={autoScalingLevel}
                  onValueChange={setAutoScalingLevel}
                  className="w-full"
                />
              </div>
              <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                <p className="text-sm text-success font-medium">
                  Projected savings: ${Math.round((autoScalingLevel[0] / 100) * 300)}/month
                </p>
              </div>
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
                    ✓ Archive old data to cheaper storage tiers
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Estimated savings: $8/month
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
                  8
                </div>
                <p className="text-sm text-muted-foreground">per month</p>
              </div>

              <div className="text-center">
                <div className="text-2xl font-bold text-primary">
                  96
                </div>
                <p className="text-sm text-muted-foreground">per year</p>
              </div>

              <div className="text-center">
                <div className="text-xl font-bold text-eco flex items-center justify-center space-x-2">
                  <Leaf className="h-5 w-5" />
                  <span>{projectedSavings.co2} tons</span>
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