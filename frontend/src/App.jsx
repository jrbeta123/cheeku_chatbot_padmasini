import { Routes, Route, Navigate } from "react-router-dom";

import Login from "./components/Login";
import Chatbot from "./components/Chatbot";

function App() {
    return (
        <Routes>
            <Route path="/" element={<Login />} />
            <Route path="/index.html" element={<Navigate to="/" replace />} />
            <Route path="/home" element={<Chatbot />} />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

export default App;