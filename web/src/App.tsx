import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Layout from "@/components/layout/Layout";
import Workbench from "@/pages/Workbench";
import Library from "@/pages/Library";
import PageView from "@/pages/PageView";
import Icons from "@/pages/Icons";
import Characters from "@/pages/Characters";
import Examples from "@/pages/Examples";
import Exercises from "@/pages/Exercises";
import MathStructure from "@/pages/MathStructure";
import Locate from "@/pages/Locate";
import Corrections from "@/pages/Corrections";
import Review from "@/pages/Review";
import GoldenSamples from "@/pages/GoldenSamples";
import Specs from "@/pages/Specs";
import Status from "@/pages/Status";
import TeacherBook from "@/pages/TeacherBook";
import Verify from "@/pages/Verify";
import OfficialLessonsPage from "@/pages/OfficialLessons";
import LessonAnalysisPage from "@/pages/LessonAnalysis";
import DocIntelligence from "@/pages/DocIntelligence";

export default function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Workbench />} />
          <Route path="/library" element={<Library />} />
          <Route path="/library/page/:pageId" element={<PageView />} />
          <Route path="/icons" element={<Icons />} />
          <Route path="/characters" element={<Characters />} />
          <Route path="/examples" element={<Examples />} />
          <Route path="/exercises" element={<Exercises />} />
          <Route path="/math-structure" element={<MathStructure />} />
          <Route path="/locate" element={<Locate />} />
          <Route path="/corrections" element={<Corrections />} />
          <Route path="/review" element={<Review />} />
          <Route path="/golden-samples" element={<GoldenSamples />} />
          <Route path="/specs" element={<Specs />} />
          <Route path="/status" element={<Status />} />
          {/* 任务二：教师用书结构化资料库 + 教材解析能力验证 */}
          <Route path="/teacher-book" element={<TeacherBook />} />
          <Route path="/verify" element={<Verify />} />
          {/* 任务三：正式课时划分与内容归属 */}
          <Route path="/official-lessons" element={<OfficialLessonsPage />} />
          {/* 任务四：课时内部教材内容关系与练习结构分析 */}
          <Route path="/lesson-analysis" element={<LessonAnalysisPage />} />
          {/* 任务五：document-intelligence 整册解析融合 */}
          <Route path="/doc-intelligence" element={<DocIntelligence />} />
        </Routes>
      </Layout>
    </Router>
  );
}
