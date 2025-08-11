INTENT_CLASSIFIER_PROMPT = (
    "You are an AI assistant processing inbound emails for a healthcare clinic. "
    "Read the user's email reply and classify its primary intent. "
    "You must choose one of the following four intents only: "
    "booking_request, service_denial, irrelevant_confused, question. "
    "Respond with only the chosen intent string and nothing else. "
    "Email: '{reply_email_body}'"
)

ALLOWED_INTENTS = {"booking_request", "service_denial", "irrelevant_confused", "question"}

# Knowledge base QA
KB_TEXT = (
    "### Welcome to Bright Smile Clinic - Your Dental Health Partner\n\n"
    "**About Us:**\n"
    "Bright Smile Clinic (Clínica Sorriso Brilhante) is a premier dental care center located in the heart of São Paulo. Our mission is to provide exceptional, personalized dental care in a comfortable and modern environment. Our team of highly skilled and compassionate dental professionals is dedicated to helping you achieve and maintain a healthy, beautiful smile for life. We use state-of-the-art technology to ensure the best possible outcomes for our patients.\n\n"
    "---\n\n"
    "### Our Services\n\n"
    "**1. Dental Implants (Implantes Dentários):**\n\n"
    "- **What it is:** A dental implant is a permanent solution for replacing missing teeth. It consists of a titanium post that is surgically placed into the jawbone, acting as an artificial tooth root. A custom-made crown is then attached to the post, perfectly matching your natural teeth.\n"
    "- **Who it's for:** Ideal for individuals who have lost one or more teeth due to injury, decay, or periodontal disease.\n"
    "- **Benefits:** Implants look, feel, and function just like natural teeth. They are durable, long-lasting, and help preserve jawbone structure, preventing the sunken-face look associated with missing teeth.\n\n"
    "**2. Veneers (Lentes de Contato Dental):**\n\n"
    "- **What it is:** Veneers are ultra-thin, custom-made shells of tooth-colored porcelain or composite resin that are bonded to the front surface of teeth. They are a cosmetic solution to improve your smile's appearance.\n"
    "- **Who it's for:** Perfect for patients looking to correct issues like chipped, stained, misaligned, uneven, or abnormally spaced teeth.\n"
    "- **Benefits:** Veneers provide a dramatic and immediate smile makeover. They are stain-resistant and can completely transform the shape, color, and symmetry of your smile.\n\n"
    "**3. Teeth Whitening (Clareamento Dental):**\n\n"
    "- **What it is:** A professional cosmetic procedure designed to remove stains and discoloration from your teeth, making them several shades whiter. We offer both in-office whitening for immediate results and custom take-home kits for your convenience.\n"
    "- **Who it's for:** Anyone who wants to brighten their smile and remove stains caused by coffee, tea, red wine, smoking, or aging.\n"
    "- **Benefits:** It's one of the fastest, most effective, and safest ways to enhance your smile's appearance. A brighter smile can significantly boost your confidence.\n\n"
    "**4. Root Canal Treatment (Tratamento de Canal):**\n\n"
    "- **What it is:** A procedure to save a tooth that is severely infected or decayed. It involves removing the infected or inflamed pulp (the living tissue inside the tooth), cleaning and disinfecting the inner chambers, and then filling and sealing it.\n"
    "- **Who it's for:** Necessary for patients experiencing a severe toothache, prolonged sensitivity to heat or cold, or a dental abscess caused by infection deep within the tooth.\n"
    "- **Benefits:** The primary benefit is that it saves your natural tooth, preventing the need for extraction. It relieves pain and eliminates the infection, restoring the tooth to full function.\n\n"
    "**5. Wisdom Tooth Extraction (Extração de Dente do Siso):**\n\n"
    "- **What it is:** The surgical removal of one or more of the third molars, commonly known as wisdom teeth. These are the last teeth to erupt, usually in the late teens or early twenties.\n"
    "- **Who it's for:** Recommended when wisdom teeth are impacted (stuck in the jaw), erupting at an angle, causing pain, crowding other teeth, or leading to infection and decay due to being difficult to clean.\n"
    "- **Benefits:** Extraction prevents future pain, infection, and damage to adjacent teeth. It helps maintain the alignment of your existing teeth and overall oral health.\n\n"
    "---\n\n"
    "### Frequently Asked Questions (FAQs)\n\n"
    "- **Q: Do you accept new patients?**\n"
    "    - A: Yes, we are always happy to welcome new patients to our clinic.\n"
    "- **Q: What should I do in a dental emergency?**\n"
    "    - A: Please call our main clinic number immediately. We set aside time for emergency appointments every day.\n"
)

KB_QA_PROMPT = (
    "You are a specialized AI assistant for the Bright Smile Clinic. Your task is to answer a patient's question based exclusively on the provided knowledge base.\n\n"
    "RULES:\n\n"
    "1. Read the user's [QUESTION] and carefully search the [KNOWLEDGE_BASE] text for the answer.\n"
    "2. If you find a clear and direct answer, provide only that information.\n"
    "3. If the answer is not found, you MUST respond with the single, exact string: NO_ANSWER.\n"
    "4. Do not use external knowledge or make assumptions. Your knowledge is strictly limited to the text provided.\n\n"
    "[KNOWLEDGE_BASE]:\n\n{knowledge_base_text}\n\n"
    "[QUESTION]:\n\n{patient_question}"
)
