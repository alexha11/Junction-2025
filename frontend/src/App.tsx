import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import OperationsPortal from "./pages/OperationsPortal";
import ProofDashboard from "./pages/ProofDashboard";

const navLinks = [
	{ to: "/", label: "Live operations" },
	{ to: "/proof", label: "Proof of performance" },
];

const navClassName = ({ isActive }: { isActive: boolean }) =>
	`rounded-full px-4 py-2 text-sm font-semibold transition hover:text-white ${
		isActive
			? "bg-brand-accent/20 text-brand-accent shadow-inner"
			: "text-slate-400"
	}`;

function App() {
	return (
		<BrowserRouter>
			<div className="min-h-screen bg-brand-base/95 px-4 py-8 text-slate-100 sm:px-6 lg:px-12">
				<div className="mx-auto max-w-7xl space-y-6 pb-12">
					<nav className="glass-card flex flex-wrap items-center justify-between gap-4">
						<div>
							<p className="text-xs font-semibold uppercase tracking-[0.35em] text-brand-valmet">
								HSY x Valmet Optimizer
							</p>
							<p className="text-lg font-semibold text-white">
								Operations cockpit
							</p>
						</div>
						<div className="flex flex-wrap gap-2">
							{navLinks.map((link) => (
								<NavLink
									key={link.to}
									to={link.to}
									className={navClassName}
								>
									{link.label}
								</NavLink>
							))}
						</div>
					</nav>
					<Routes>
						<Route path="/" element={<OperationsPortal />} />
						<Route path="/proof" element={<ProofDashboard />} />
					</Routes>
				</div>
			</div>
		</BrowserRouter>
	);
}

export default App;
