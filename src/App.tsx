import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { Overview } from "@/pages/Overview";
import { Alerts } from "@/pages/Alerts";
import { Resources } from "@/pages/Resources";
import { CostOptimization } from "@/pages/CostOptimization";
import { Security } from "@/pages/Security";
import { Settings } from "@/pages/Settings";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/resources" element={<Resources />} />
            <Route path="/cost-optimization" element={<CostOptimization />} />
            <Route path="/security" element={<Security />} />
            <Route path="/settings" element={<Settings />} />
            {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
