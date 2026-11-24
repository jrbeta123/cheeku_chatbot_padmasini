import { Routes, Route, Navigate } from "react-router-dom";

import Login from "./components/Login";
import Home from "./components/Home";

function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/home" element={<Home />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;