import { IncidentWorkspace } from "@/components/incident/incident-workspace";

export default async function IncidentPage({
  params,
}: PageProps<"/incidents/[reference]">) {
  const { reference } = await params;
  return <IncidentWorkspace initialReference={reference} />;
}
