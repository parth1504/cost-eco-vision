import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { 
  DollarSign, 
  Leaf, 
  TrendingUp, 
  TrendingDown,
  Activity as ActivityIcon,
  Server,
  AlertTriangle,
  CheckCircle
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { mockSavingsData, type Activity, type Recommendation } from "@/lib/mockData";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

interface SavingsData {
  monthly: number;
  yearly: number;
  co2Reduced: number;
  totalOptimizations: number;
  chartData: { month: string; savings: number }[];
}

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

export function Overview() {
  const [savingsData, setSavingsData] = useState<SavingsData>(mockSavingsData);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchOverviewData = async () => {
      try {
        const response = await fetch("http://localhost:8000/overview");
        
        if (!response.ok) {
          throw new Error("Failed to fetch overview data");
        }

        const result = await response.json();
        const data = result.data;

        setSavingsData(data.savingsData);
        setActivities(data.activities);
        setRecommendations(data.recommendations);
        setIsLoading(false);
      } catch (error) {
        console.error("❌ Failed to fetch overview data from backend:", error);
        console.log("⚠️ Falling back to local mock data");
        toast.error("Backend server not available", {
          description: "Using local data. Start the FastAPI server to see live data.",
        });
        // Keep using the initial mock data as fallback
        setIsLoading(false);
      }
    };

    fetchOverviewData();
  }, []);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
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
        <h1 className="text-3xl font-bold text-foreground">Dashboard Overview</h1>
        <p className="text-muted-foreground mt-2">
          Real-time insights from your AI-powered cloud optimization agent
        </p>
      </motion.div>

      {/* Summary Cards */}
      <motion.div 
        variants={itemVariants}
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6"
      >
        {/* Monthly Savings */}
        <Card className="metric-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Savings</CardTitle>
            <DollarSign className="h-4 w-4 text-success" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">
              {isLoading ? "..." : formatCurrency(activities.reduce((sum, activity) => sum + activity.savings, 0))}
            </div>
            <div className="flex items-center space-x-2 text-xs text-muted-foreground">
              <TrendingUp className="h-3 w-3 text-success" />
              <span>+12% from last month</span>
            </div>
          </CardContent>
        </Card>

        {/* Yearly Forecast */}
        <Card className="metric-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Yearly Forecast</CardTitle>
            <TrendingUp className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-primary">
              {isLoading ? "..." : formatCurrency(activities.reduce((sum, activity) => sum + activity.savings, 0) * 12)}
            </div>
            <div className="flex items-center space-x-2 text-xs text-muted-foreground">
              <span>Projected annual savings</span>
            </div>
          </CardContent>
        </Card>

        {/* CO₂ Reduction */}
        <Card className="metric-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CO₂ Reduced</CardTitle>
            <Leaf className="h-4 w-4 text-eco" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-eco">
              {isLoading ? "..." : `${Math.round(savingsData.co2Reduced * activities.length)} kgs`}
            </div>
            <div className="flex items-center space-x-2 text-xs text-muted-foreground">
              <TrendingUp className="h-3 w-3 text-eco" />
              <span>Environmental impact</span>
            </div>
          </CardContent>
        </Card>

        {/* Total Optimizations */}
        <Card className="metric-card">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Optimizations</CardTitle>
            <Server className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-foreground">
              {isLoading ? "..." : activities.length}
            </div>
            <div className="flex items-center space-x-2 text-xs text-muted-foreground">
              <CheckCircle className="h-3 w-3 text-success" />
              <span>Resources optimized</span>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Chart and Recommendations */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Savings Chart */}
        <motion.div variants={itemVariants} className="lg:col-span-2">
          <Card className="chart-container">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <ActivityIcon className="h-5 w-5" />
                <span>Cost Savings Over Time</span>
              </CardTitle>
              <CardDescription>
                Monthly cost optimization trends
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={savingsData.chartData}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                    <XAxis dataKey="month" />
                    <YAxis tickFormatter={(value) => `$${value}`} />
                    <Tooltip 
                      formatter={(value) => [formatCurrency(value as number), "Savings"]}
                      labelStyle={{ color: 'hsl(var(--foreground))' }}
                      contentStyle={{ 
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px'
                      }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="savings" 
                      stroke="hsl(var(--success))" 
                      strokeWidth={3}
                      dot={{ fill: 'hsl(var(--success))', strokeWidth: 2, r: 4 }}
                      activeDot={{ r: 6 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        {/* Recent Activities */}
        <motion.div variants={itemVariants}>
          <Card className="dashboard-card h-full">
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <ActivityIcon className="h-5 w-5" />
                <span>Recent Actions</span>
              </CardTitle>
              <CardDescription>
                Latest agent optimizations
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {activities.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-start space-x-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className={`mt-1 h-2 w-2 rounded-full ${
                    activity.type === 'Cost' ? 'bg-success' :
                    activity.type === 'Security' ? 'bg-primary' : 'bg-warning'
                  }`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {activity.action}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatTimestamp(activity.timestamp)}
                    </p>
                    {activity.savings > 0 && (
                      <p className="text-xs text-success font-medium">
                        Saved {formatCurrency(activity.savings)}/month
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Recommendations Table */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="h-5 w-5" />
                <span>Top Recommendations</span>
              </div>
              <Badge variant="secondary">{recommendations.length} pending</Badge>
            </CardTitle>
            <CardDescription>
              AI-powered optimization suggestions for your infrastructure
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Resource</th>
                    <th>Issue</th>
                    <th>Recommendation</th>
                    <th>Estimated Savings</th>
                    <th>Impact</th>
                    {/* <th>Action</th> */}
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((rec) => (
                    <tr key={rec.id}>
                      <td>
                        <div>
                          <p className="font-medium text-foreground">{rec.resource}</p>
                          <p className="text-sm text-muted-foreground">{rec.resourceType}</p>
                        </div>
                      </td>
                      <td>
                        <p className="text-sm text-foreground">{rec.issue}</p>
                      </td>
                      <td>
                        <p className="text-sm text-foreground max-w-xs">{rec.recommendation}</p>
                      </td>
                      <td>
                        <p className="font-medium text-success">
                          {rec.estimatedSavings > 0 ? formatCurrency(rec.estimatedSavings) : 'Security Fix'}
                        </p>
                        <p className="text-xs text-muted-foreground">/month</p>
                      </td>
                      <td>
                        <Badge
                          className={
                            rec.impact === 'High' ? 'status-critical' :
                            rec.impact === 'Medium' ? 'status-warning' : 'status-success'
                          }
                        >
                          {rec.impact}
                        </Badge>
                      </td>
                      {/* <td>
                        <Button size="sm" className="action-success">
                          Apply Fix
                        </Button>
                      </td> */}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  );
}