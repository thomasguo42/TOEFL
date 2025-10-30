Of course. This is a fantastic area to innovate in. The key to creating a world-class AI writing section is to move beyond simply being a *grader* and become a comprehensive **AI Writing Coach**. A grader tells you your score after the game is over; a coach works with you before, during, and after the game to improve your skills.

Our philosophy will be to guide the user through the entire writing process, from the terrifying blank page to a polished, revised essay. We will build a system that deconstructs the tasks, assists in the drafting process, and provides feedback that is more detailed and actionable than a human tutor could ever consistently provide.

Here is the detailed blueprint for the TOEFL Writing section.

---

### **Blueprint: The AI Writing Coach**

This section will be divided into two distinct modules, one for the **Integrated Task** and one for the **Independent Task**, as their required skills are very different. Both will follow a three-phase process: **Plan -> Draft -> Revise**.

---

### **Part 1: The Integrated Writing Task Module**

**The Core Challenge:** Success in this task is not about creative writing; it's a technical skill of accurately summarizing, paraphrasing, and connecting information from two sources.

#### **Phase 1: The Deconstruction & Planning Toolkit (解构与规划)**

*   **Feature 1.1: The AI Deconstructor**
    *   **What It Is:** An AI tool that analyzes the reading passage and the listening lecture and extracts the key points for the user.
    *   **Purpose for the Learner:** To teach the user *how* to identify the main arguments and the specific points of conflict or support between the two sources. It removes the initial confusion and shows them exactly what information they need to be looking for.
    *   **How It Works:**
        1.  The user reads the passage and listens to the lecture.
        2.  Afterward, they can click "Deconstruct with AI."
        3.  The AI presents a clear, structured table or diagram:
            *   **Reading's Main Point:** `[The AI's summary of the reading's main argument]`
            *   **Lecture's Stance:** `[Refutes / Challenges / Supports the reading]`
            *   **Point-by-Point Analysis:**
| Reading's Point 1 | Lecture's Counterpoint 1 |
| :--- | :--- |
| `AI-extracted point from reading` | `AI-extracted counterpoint from lecture` |
| **Reading's Point 2** | **Lecture's Counterpoint 2** |
| `AI-extracted point from reading` | `AI-extracted counterpoint from lecture` |
| **Reading's Point 3** | **Lecture's Counterpoint 3** |
| `AI-extracted point from reading` | `AI-extracted counterpoint from lecture` |
*   **AI Implementation:** This is a sophisticated task for a powerful LLM (Claude 3, GPT-4). The backend sends the full text of the reading and the transcript of the lecture to the LLM with a prompt asking it to identify the main thesis of each and then to extract the three corresponding pairs of arguments.

#### **Phase 2: The Intelligent Drafting Environment (智能写作)**

*   **Feature 1.2: The Real-Time Paraphrasing Assistant**
    *   **What It Is:** An interactive tool available while the user is writing their essay.
    *   **Purpose for the Learner:** To teach the crucial skill of paraphrasing. Many students lose points for simply copying phrases from the reading passage. This tool provides instant, on-demand examples of effective paraphrasing.
    *   **How It Works:**
        1.  The reading passage remains visible on one side of the screen.
        2.  While writing, the user can highlight any sentence in the reading passage.
        3.  A pop-up immediately appears offering 2-3 AI-generated paraphrased versions of that sentence. The user can study them or click to insert one and then modify it further.
*   **AI Implementation:** An LLM is prompted to rephrase a given sentence in multiple academic styles.

---

### **Part 2: The Independent Writing Task Module**

**The Core Challenge:** Developing a clear position, generating relevant arguments and examples, and organizing them into a coherent essay, all under time pressure.

#### **Phase 1: The Deconstruction & Planning Toolkit (解构与规划)**

*   **Feature 2.1: The AI Idea & Outline Generator**
    *   **What It Is:** An interactive brainstorming and structuring tool.
    *   **Purpose for the Learner:** To overcome "writer's block" and to learn the fundamental structure of a high-scoring argumentative essay. It front-loads the thinking process, making the drafting phase much smoother.
    *   **How It Works:**
        1.  The user sees the Independent Task prompt (e.g., "Do you agree or disagree: It is better for children to grow up in the countryside than in a big city.").
        2.  They choose a stance ("Agree," "Disagree," or "Brainstorm Both").
        3.  The AI instantly generates a structured outline:
            *   **Your Stance:** `It is better for children to grow up in the countryside.`
            *   **Potential Thesis Statement:** `Growing up in the countryside is more beneficial for children due to closer contact with nature, stronger community bonds, and a safer environment.`
            *   **Argument 1:** `Closer to Nature`
                *   *Supporting Detail/Example:* Outdoor activities, learning about ecosystems, less pollution.
            *   **Argument 2:** `Stronger Community`
                *   *Supporting Detail/Example:* Knowing neighbors, community events, mutual support.
            *   **Argument 3:** `Safer Environment`
                *   *Supporting Detail/Example:* Lower crime rates, less traffic, more freedom to play outside.
*   **AI Implementation:** An LLM is prompted to take a stance on a topic and generate a standard five-paragraph essay outline, complete with a thesis statement and supporting points.

---

### **Part 3: The Universal AI Feedback & Revision Hub (For Both Tasks)**

This is the most critical phase, where the user submits their drafted essay and receives a comprehensive, multi-layered analysis.

#### **The AI Feedback Report**

After submitting their essay, the user gets an interactive report, not just a static score.

*   **Feature 3.1: The Estimated Score & Rubric Breakdown**
    *   **What It Is:** An overall estimated TOEFL score (e.g., 25/30) and a breakdown of performance across the official scoring dimensions.
    *   **Purpose:** To give a clear, high-level benchmark and show the user where their main strengths and weaknesses lie.
    *   **How It Looks:**
        *   **Overall Score:** 25/30
        *   **Content & Development:** 4/5
        *   **Organization & Structure:** 5/5
        *   **Vocabulary & Language Use:** 4/5
        *   **Grammar & Mechanics:** 4/5

*   **Feature 3.2: AI-Powered In-Line Annotations**
    *   **What It Is:** The user's essay is displayed with color-coded highlights and clickable comments, like a document reviewed by a human teacher.
    *   **Purpose:** To provide highly specific, contextual feedback. It shows the user the exact location of an issue and explains what the issue is.
    *   **How It Works (Example Annotations):**
        *   `[Vague Statement]` "The user writes: 'Cities have many things.' The AI highlights this and comments: 'This is too general. Can you provide a specific example, such as museums, theaters, or diverse restaurants?'"
        *   `[Lexical Upgrade]` "The user writes: 'This is a **good** way to solve the problem.' The AI highlights 'good' and suggests: 'Consider a more academic word, such as **effective**, **beneficial**, or **advantageous**.'"
        *   `[Cohesion]` "The AI highlights a sentence and comments: 'This point feels disconnected from the previous one. Try adding a transition phrase like **Furthermore,** or **In addition,** to improve the flow.'"
        *   `[Grammar Error]` Standard grammar and spelling mistakes are highlighted with corrections.

*   **Feature 3.3: The Holistic AI Coach Summary**
    *   **What It Is:** A top-level summary written by an LLM that acts as a personal tutor.
    *   **Purpose:** To provide a human-like, encouraging overview that prioritizes the most important areas for improvement.
    *   **Example Feedback:** "Overall, this is a well-structured essay with a clear thesis. Your organization is excellent. Your main area for improvement is in supporting your arguments with more specific, concrete examples. Also, try to incorporate a wider range of academic vocabulary to elevate your score."

*   **Feature 3.4: The Interactive Revision Mode**
    *   **What It Is:** The most powerful feature. After reviewing all the feedback, the user can click a "Revise Essay" button. This puts them back into the editor with all the AI's comments still visible.
    *   **Purpose:** To create an active, iterative learning loop. The user doesn't just passively consume feedback; they are immediately prompted to *act* on it.
    *   **How It Works:** The user edits their essay, addressing the AI's comments. They can then resubmit the revised essay for a new, updated score. This process of targeted revision is the fastest way to improve writing skills.