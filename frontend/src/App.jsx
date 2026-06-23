import { Routes, Route, Navigate } from "react-router-dom";
import { BrowserRouter } from "react-router-dom";

/* css */
import "./css/index.css";
import "./css/App.css";
import "./css/garim.css";
import { GarimRouteProvider } from "./context/GarimRouteContext.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import { NotificationProvider } from "./context/NotificationContext.jsx";
import { ThemeProvider } from "./context/ThemeContext.jsx";
import { garimPages } from "./data/garim/pages";

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
      <AuthProvider>
      <NotificationProvider>
        <Routes>
        {garimPages.map((route) => (
          <Route
            key={route.path}
            path={route.path}
            element={
              <GarimRouteProvider route={route}>
                <route.component />
              </GarimRouteProvider>
            }
          />
        ))}
        <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </NotificationProvider>
      </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}

export default App;
