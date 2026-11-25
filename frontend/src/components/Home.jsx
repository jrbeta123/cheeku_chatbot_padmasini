import Header from "../navigation/Header";
import Footer from "../navigation/Footer";
import Chatbot from "./Chatbot";
import "./Home.css";git

function Home() {
  return (
    <div id="home">
      <Header />

      <main id="chat">
        <Chatbot />
      </main>

      <Footer />
    </div>
  );
}

export default Home;