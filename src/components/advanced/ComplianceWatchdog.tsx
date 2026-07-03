import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Shield, Key, RotateCcw, TrendingUp, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer } from "recharts";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function ComplianceWatchdog() {
  const [securityScore, setSecurityScore] = useState(0);
  const [scoreTrend, setScoreTrend] = useState<any[]>([]);
  const [weeklyData, setWeeklyData] = useState<any[]>([]);
  const [keys, setKeys] = useState<any[]>([]);
  const [compliance, setCompliance] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    fetchSecurityData();
  }, []);

  const fetchSecurityData = async () => {
    try {
      console.log("🔄 Fetching security data from backend...");
      const response = await fetch("http://localhost:8000/security/data");
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Successfully fetched security data:", data);
      setSecurityScore(data.score.current);
      setScoreTrend(data.score.trend);
      setWeeklyData(data.score.weeklyData || []);
      setKeys(data.keys);
      setCompliance(data.compliance);
    } catch (error) {
      console.error("❌ Failed to fetch security data:", error);
      setSecurityScore(0);
      setScoreTrend([]);
      setWeeklyData([]);
      setKeys([]);
      setCompliance({});
    } finally {
      setLoading(false);
    }
  };

  const getKeyStatusColor = (status: string) => {
    switch (status) {
      case 'Expired': return 'status-critical';
      case 'Unused': return 'status-warning';
      default: return 'status-success';
    }
  };

  const handleRotateKey = (keyId: string) => {
    setKeys(prev => prev.map(key =>
      key.id === keyId
        ? { ...key, status: "Active" as const, lastUsed: new Date().toISOString() }
        : key
    ));

    // Improve security score
    const newScore = Math.min(100, securityScore + 5);
    setSecurityScore(newScore);

    toast({
      title: "🔄 Key Rotated Successfully",
      description: "Security key has been rotated and security score improved by +5 points.",
    });
  };

  const unusedKeys = keys.filter(k => k.status === 'Unused').length;
  const expiredKeys = keys.filter(k => k.status === 'Expired').length;

  if (loading) {
    return <div className="text-center text-muted-foreground">Loading security data...</div>;
  }

  return (
    <div className="space-y-6">
      {/* Security Health Score */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Shield className="h-5 w-5 text-success" />
              <span>Cloud Security Health Score</span>
            </CardTitle>
            <CardDescription>
              Overall security posture with weekly trending
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="space-y-4">
                <div className="text-center">
                  <div className="relative inline-block">
                    <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 100 100">
                      <circle
                        cx="50"
                        cy="50"
                        r="40"
                        stroke="hsl(var(--muted))"
                        strokeWidth="8"
                        fill="none"
                      />
                      <motion.circle
                        cx="50"
                        cy="50"
                        r="40"
                        stroke="hsl(var(--success))"
                        strokeWidth="8"
                        fill="none"
                        strokeDasharray={`${2 * Math.PI * 40}`}
                        strokeDashoffset={`${2 * Math.PI * 40 * (1 - securityScore / 100)}`}
                        initial={{ strokeDashoffset: 2 * Math.PI * 40 }}
                        animate={{ strokeDashoffset: 2 * Math.PI * 40 * (1 - securityScore / 100) }}
                        transition={{ duration: 1, ease: "easeOut" }}
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="text-center">
                        <div className="text-3xl font-bold text-success">{securityScore}</div>
                        <div className="text-xs text-muted-foreground">Score</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4 text-center">
                  <div className="p-3 bg-success/5 border border-success/20 rounded-lg">
                    <TrendingUp className="h-5 w-5 text-success mx-auto mb-1" />
                    <p className="text-sm font-medium text-success">+3</p>
                    <p className="text-xs text-muted-foreground">This week</p>
                  </div>
                  <div className="p-3 bg-muted/30 rounded-lg">
                    <Shield className="h-5 w-5 text-foreground mx-auto mb-1" />
                    <p className="text-sm font-medium">Industry Avg</p>
                    <p className="text-xs text-muted-foreground">73</p>
                  </div>
                </div>
              </div>

              <div>
                <h4 className="font-medium mb-3">Weekly Security Trend</h4>
                <div className="h-32">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={weeklyData}>
                      <XAxis dataKey="day" axisLine={false} tickLine={false} />
                      <YAxis hide />
                      <Line
                        type="monotone"
                        dataKey="score"
                        stroke="hsl(var(--success))"
                        strokeWidth={3}
                        dot={{ fill: 'hsl(var(--success))', strokeWidth: 2, r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Unused Keys & Service Accounts */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Key className="h-5 w-5 text-warning" />
                <span>Security Keys & Accounts</span>
              </div>
              <div className="flex items-center space-x-2">
                {unusedKeys > 0 && (
                  <Badge className="status-warning">
                    {unusedKeys} unused
                  </Badge>
                )}
                {expiredKeys > 0 && (
                  <Badge className="status-critical">
                    {expiredKeys} expired
                  </Badge>
                )}
              </div>
            </CardTitle>
            <CardDescription>
              Manage unused keys and service accounts to improve security posture
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {keys.map((key) => (
                <div
                  key={key.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/30 transition-colors"
                >
                  <div className="flex items-center space-x-4">
                    <div className="flex items-center justify-center w-10 h-10 bg-muted/50 rounded-lg">
                      <Key className="h-5 w-5 text-muted-foreground" />
                    </div>
                    
                    <div>
                      <div className="flex items-center space-x-2 mb-1">
                        <p className="font-medium text-foreground">{key.name}</p>
                        <Badge variant="outline" className="text-xs">{key.type}</Badge>
                        <Badge className={getKeyStatusColor(key.status)}>
                          {key.status}
                        </Badge>
                      </div>
                      <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                        <span>Last used: {new Date(key.lastUsed).toLocaleDateString()}</span>
                        <span>
                          {key.expiresIn > 0 ? `Expires in ${key.expiresIn} days` : `Expired ${Math.abs(key.expiresIn)} days ago`}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2">
                    {key.status !== 'Active' && (
                      <Button
                        size="sm"
                        onClick={() => handleRotateKey(key.id)}
                        className="action-primary"
                      >
                        <RotateCcw className="h-4 w-4 mr-2" />
                        Rotate Key
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {keys.filter(k => k.status !== 'Active').length === 0 && (
              <div className="text-center py-8">
                <Shield className="h-12 w-12 text-success mx-auto mb-4" />
                <p className="text-lg font-medium text-success">All keys are secure!</p>
                <p className="text-sm text-muted-foreground">No unused or expired keys detected</p>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Security Recommendations */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <AlertTriangle className="h-5 w-5 text-warning" />
              <span>Security Recommendations</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Shield className="h-4 w-4 text-primary" />
                  <span className="font-medium text-primary">Key Rotation Policy</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Implement automated key rotation every 90 days to improve security score by 10-15 points.
                </p>
              </div>

              <div className="p-4 bg-success/5 border border-success/20 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <TrendingUp className="h-4 w-4 text-success" />
                  <span className="font-medium text-success">Security Posture Improvement</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  Your security score has improved by 3 points this week. 
                  Keep up the great work!
                </p>
              </div>

              <div className="p-4 bg-warning/5 border border-warning/20 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Key className="h-4 w-4 text-warning" />
                  <span className="font-medium text-warning">Action Required</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {unusedKeys + expiredKeys} security credentials need attention. 
                  Rotating them will improve your security score and reduce compliance risks.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}