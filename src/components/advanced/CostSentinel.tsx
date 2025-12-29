import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Trophy, DollarSign, Users, Star } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
};

export function CostSentinel() {
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [totalSavings, setTotalSavings] = useState(0);
  const [loading, setLoading] = useState(true);
  
  const forecastData = {
    thisMonth: 3245,
    nextMonth: 2890,
    savings: 355,
    confidence: 94
  };

  useEffect(() => {
    fetchLeaderboardData();
  }, []);

  const fetchLeaderboardData = async () => {
    try {
      console.log("🔄 Fetching leaderboard data from backend...");
      const response = await fetch("http://localhost:8000/leaderboard");
      
      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
      }
      
      const data = await response.json();
      console.log("✅ Successfully fetched leaderboard data:", data);
      setLeaderboard(data.leaderboard);
      setTotalSavings(data.totalSavings);
    } catch (error) {
      console.error("❌ Failed to fetch leaderboard data:", error);
      setLeaderboard([]);
      setTotalSavings(0);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Monthly Bill Prediction */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <TrendingUp className="h-5 w-5 text-primary" />
              <span>Monthly Bill Prediction</span>
            </CardTitle>
            <CardDescription>
              AI-powered cost forecasting with optimization recommendations
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-4 bg-muted/30 rounded-lg">
                <p className="text-sm text-muted-foreground">This Month</p>
                <p className="text-2xl font-bold text-foreground">29</p>
              </div>
              <div className="text-center p-4 bg-success/5 border border-success/20 rounded-lg">
                <p className="text-sm text-muted-foreground">Next Month (Optimized)</p>
                <p className="text-2xl font-bold text-success">31</p>
              </div>
            </div>
            
            <div className="flex items-center justify-between p-4 bg-primary/5 border border-primary/20 rounded-lg">
              <div className="flex items-center space-x-2">
                <DollarSign className="h-5 w-5 text-primary" />
                <span className="font-medium">Predicted Savings</span>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-primary">12</p>
                <p className="text-xs text-muted-foreground">{forecastData.confidence}% confidence</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Gamified Leaderboard */}
      <motion.div variants={itemVariants}>
        <Card className="dashboard-card">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Trophy className="h-5 w-5 text-warning" />
              <span>Top Savers This Month</span>
            </CardTitle>
            <CardDescription>
              Teams and individuals making the biggest impact on cost optimization
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center text-muted-foreground">Loading leaderboard...</div>
            ) : (
              <>
                <div className="space-y-4">
                  {leaderboard.map((entry, index) => (
                <motion.div
                  key={entry.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className={`flex items-center justify-between p-4 rounded-lg border ${
                    entry.rank === 1 ? 'bg-warning/5 border-warning/20' :
                    entry.rank === 2 ? 'bg-muted/50 border-muted' :
                    entry.rank === 3 ? 'bg-orange-500/5 border-orange-500/20' :
                    'bg-muted/30'
                  }`}
                >
                  <div className="flex items-center space-x-4">
                    <div className={`flex items-center justify-center w-8 h-8 rounded-full ${
                      entry.rank === 1 ? 'bg-warning text-warning-foreground' :
                      entry.rank === 2 ? 'bg-muted-foreground text-muted' :
                      entry.rank === 3 ? 'bg-orange-500 text-white' :
                      'bg-muted text-muted-foreground'
                    }`}>
                      {entry.rank <= 3 ? (
                        <Trophy className="h-4 w-4" />
                      ) : (
                        <span className="text-sm font-bold">{entry.rank}</span>
                      )}
                    </div>
                    
                    <div>
                      <p className="font-medium text-foreground">{entry.user}</p>
                      <div className="flex items-center space-x-2 text-sm text-muted-foreground">
                        <Users className="h-3 w-3" />
                        <span>{entry.team}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="text-right">
                    <p className="font-bold text-success">${entry.savings}</p>
                    <div className="flex items-center space-x-1 text-xs text-muted-foreground">
                      <Star className="h-3 w-3" />
                      <span>{entry.optimizations} optimizations</span>
                    </div>
                    </div>
                  </motion.div>
                ))}
              </div>
              
              <div className="mt-4 p-3 bg-primary/5 border border-primary/20 rounded-lg text-center">
                <p className="text-sm text-primary font-medium">
                  🎉 Collective team savings this month: ${totalSavings.toLocaleString()}
                </p>
              </div>
            </>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}