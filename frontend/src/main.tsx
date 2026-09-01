import { createRoot } from "react-dom/client";

import App from "./App";
import { initializeTheme } from "./theme";
import "./theme.css";
import "./styles.css";
import "./panels.css";
import "./workspace/workspace.css";
import "./settings/settings.css";

initializeTheme();
createRoot(document.getElementById("root")!).render(<App />);
