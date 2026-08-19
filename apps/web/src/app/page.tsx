import { Header } from "@/components/header";
import { ServicesDashboard } from "@/components/services-dashboard";

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <Header />
      <main className="flex-1">
        <ServicesDashboard />
      </main>
    </div>
  );
}
