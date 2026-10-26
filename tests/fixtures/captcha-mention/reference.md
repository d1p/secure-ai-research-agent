Test to determine whether a user is human

This CAPTCHA (GIMPY-R, c. 2005) of "smwm" obscures its message from computer interpretation by twisting the letters and adding a slight background color gradient.

A CAPTCHA (/ˈkæp.tʃə/ KAP-chə), a type of challenge-response Turing test, aims to protect computing user-interfaces. It attempts to deter bot attacks and spam by determining whether a user is a human.[1]

The term "CAPTCHA" was coined in 2003 by Luis von Ahn, Manuel Blum, Nicholas J. Hopper, and John Langford.[2] It is a contrived acronym for "Completely Automated Public Turing test to tell Computers and Humans Apart".[3] A historically common type of CAPTCHA (displayed as reCAPTCHA v1) was first invented in 1997 by two groups working in parallel. This form of CAPTCHA requires interpreting a sequence of letters or numbers from a distorted image. Because the test is administered by a computer, in contrast to the standard Turing test that is administered by a human, CAPTCHAs are sometimes described as reverse Turing tests.[4]

Two widely-used CAPTCHA services are Google's reCAPTCHA[5][6] and Intuition Machines' hCaptcha.[7][8] Cloudflare, a major website-security service provider, reported in 2021 that it takes the average person approximately 32 seconds to complete a typical CAPTCHA challenge,[9] although an earlier estimate from Stanford University in 2018 reported a shorter solving-time of about 10 seconds.[10]

Purpose

The purpose of CAPTCHAs is to prevent bots from using services intended for human use, prevent denial-of-service attacks, prevent distortion of collected usage information, prevent automated entry of false information, and prevent data scraping. Many websites use CAPTCHA effectively to prevent bot raiding. CAPTCHAs are designed so that humans can complete them, while most robots cannot.[11] Newer CAPTCHAs look at the user's behaviour on the internet, to prove that they are a human.[12] Ideally, a CAPTCHA test only appears if the user's actions resemble those by a bot, such as if they request webpages from suspicious IP addresses, access many pages, or click links too quickly.

It has also been suggested that popular CAPTCHA services such as reCAPTCHA and hCAPTCHA had the dual purpose of serving as public tools to use humans to generate data sets for AI with tasks such as image-labelling.[13][14]

History

Since the 1980s–1990s, users have wanted to make text illegible to computers.[15] The first such people were hackers, posting about sensitive topics to Internet forums they thought were being automatically monitored on keywords. To circumvent such filters, they replaced a word with look-alike characters. HELLO could become |-|3|_|_() or )-(3££0, and others, such that a filter could not detect all of them. This later became known as leetspeak.[16]

One of the earliest commercial uses of CAPTCHAs was in the Gausebeck–Levchin test. In 2000, idrive.com began to protect its signup page[17] with a CAPTCHA and prepared to file a patent.[15] In 2001, PayPal used such tests as part of a fraud prevention strategy in which they asked humans to "retype distorted text that programs have difficulty recognizing".[18] PayPal co founder and CTO Max Levchin helped commercialize this use. AltaVista implemented an early CAPTCHA scheme to protect against fraudulent account registrations.[19][20][21]

A popular deployment of CAPTCHA technology, reCAPTCHA, was acquired by Google in 2009.[22] In addition to preventing bot fraud for its users, Google used reCAPTCHA and CAPTCHA technology to digitize the archives of The New York Times and books from Google Books in 2011.[23] While early versions required users to transcribe words or label traffic images, the current implementation of reCAPTCHA is based on collecting data on the behavior and attributes of the user, e.g. through canvas fingerprinting,[24] and using this data to assess which users are bots. Image labeling challenges are only presented when the user is determined to be "high-risk". Cloudflare's Turnstile functions similarly and is also widely used.[13] Mouse movement does not seem to affect reCAPTCHA's risk analysis.[24]

In 2026 Google announced that new versions of its reCAPTCHA software would require users to scan a QR-code with their phone, with Android users being required to have Google Play services installed on their phones. This would make solving these captchas impossible on phones without Google Play services (like those running GrapheneOS or LineageOS).[25]

Characteristics

CAPTCHAs are automated, requiring little human maintenance or intervention to administer, producing benefits in cost and reliability.[26]

Text-based CAPTCHAs are designed such that they require the simultaneous use of three separate abilities—invariant recognition, segmentation, and parsing to complete the task.[27]

Invariant recognition refers to the ability to recognize letters despite a large amount of variation in their shapes.[28]

Segmentation is the ability to separate one letter from another, made difficult in CAPTCHAs.

Parsing refers to the ability to understand the CAPTCHA holistically, in order to correctly identify each character.[29]

Each of these problems poses a significant challenge for a computer, even in isolation. Therefore, these three techniques in tandem make CAPTCHAs difficult for computers to solve.[30]

Whilst primarily used for security reasons, CAPTCHAs can also serve as a benchmark task for artificial intelligence technologies. According to an article by Ahn, Blum and Langford,[31] "any program that passes the tests generated by a CAPTCHA can be used to solve a hard unsolved AI problem".[32] They argue that the advantages of using hard AI problems as a means for security are twofold. Either the problem goes unsolved and there remains a reliable method for distinguishing humans from computers, or the problem is solved and a difficult AI problem is resolved along with it.[31]

Accessibility

See also: Web accessibility

Many websites require typing a CAPTCHA when creating an account to prevent spam. This image contains a user trying to type the CAPTCHA word "sepalbeam" to protect against automated spam.

CAPTCHAs based on reading text—or other visual-perception tasks—prevent blind or visually impaired users from accessing the protected resource.[33][34] Because CAPTCHAs are designed to be unreadable by machines, common assistive technology tools such as screen readers cannot interpret them. The use of CAPTCHA thus excludes a small percentage of users from using significant subsets of such common Web-based services as PayPal, Gmail, Orkut, Yahoo!, many forum and weblog systems, etc.[35] In certain jurisdictions, site owners could become targets of litigation if they are using CAPTCHAs that discriminate against certain people with disabilities. For example, a CAPTCHA may make a site incompatible with Section 508 in the United States.

CAPTCHAs do not have to be visual. Any hard artificial intelligence problem, such as speech recognition, can be used as CAPTCHA. Some implementations of CAPTCHAs permit users to opt for an audio CAPTCHA, such as reCAPTCHA, though a 2011 paper demonstrated a technique for defeating the popular schemes at the time.[36]

A method of improving CAPTCHA to ease the work with it was proposed by ProtectWebForm and named "Smart CAPTCHA".[37] Developers are advised to combine CAPTCHA with JavaScript. Since it is hard for most bots to parse and execute JavaScript, a combinatory method which fills the CAPTCHA fields and hides both the image and the field from human eyes was proposed.[38]

One alternative method involves displaying to the user a simple mathematical equation and requiring the user to enter the solution as verification. Although these are much easier to defeat using software, they are suitable for scenarios where graphical imagery is not appropriate, and they provide a much higher level of accessibility for blind users than the image-based CAPTCHAs. These are sometimes referred to as MAPTCHAs (M = "mathematical"). However, these may be difficult for users with a cognitive disorder, such as dyscalculia.[39]

Challenges such as a logic puzzle, or trivia question can also be used as a CAPTCHA. There is research into their resistance against countermeasures.[40]

Circumvention

Two main ways to bypass CAPTCHA include using cheap human labor to recognize them, and using machine learning to build an automated solver.[41] According to former Google "click fraud czar" Shuman Ghosemajumder, there are numerous services which solve CAPTCHAs automatically.[42]

Machine learning–based attacks

An example of a reCAPTCHA challenge from 2007, containing the words "following finding". The waviness and horizontal stroke were added to increase the difficulty of breaking the CAPTCHA with a computer program.

A CAPTCHA usually has a text box directly underneath where the user should fill out the text that they see—in this case "sclt ..was here".

There was not a systematic methodology for designing or evaluating early CAPTCHAs.[30] As a result, there were many instances in which CAPTCHAs were of a fixed length and therefore automated tasks could be constructed to successfully make educated guesses about where segmentation should take place. Other early CAPTCHAs contained limited sets of words, which made the test much easier to game[example needed] made the mistake of relying too heavily on background confusion in the image. In each case, algorithms were created that were successfully able to complete the task by exploiting these design flaws. However, light changes to the CAPTCHA could thwart them. Modern CAPTCHAs like reCAPTCHA rely on present variations of characters that are collapsed together, making them hard to segment, and they have warded off automated tasks.[43]

In October 2013, artificial intelligence company Vicarious claimed that it had developed a generic CAPTCHA-solving algorithm that was able to solve modern CAPTCHAs with character recognition rates of up to 90%.[44] However, Luis von Ahn, a pioneer of early CAPTCHA and founder of reCAPTCHA, said: "It's hard for me to be impressed since I see these every few months." 50 similar claims to that of Vicarious had been made since 2003.[45]

In August 2014 at Usenix WoOT conference, Bursztein et al. presented the first generic CAPTCHA-solving algorithm based on reinforcement learning and demonstrated its efficiency against many popular CAPTCHA schemas.[43]

In October 2018 at ACM CCS'18 conference, Ye et al. presented a deep learning-based attack that could consistently solve all 11 text captcha schemes used by the top-50 popular websites in 2018. An effective CAPTCHA solver can be trained using as few as 500 real CAPTCHAs.[46]

Human labor

It is possible to subvert CAPTCHAs by relaying them to a sweatshop of human operators who are employed to decode CAPTCHAs. A 2005 paper from a W3C working group said that they could verify hundreds per hour.[33] In 2010, the University of California at San Diego conducted a large scale study of CAPTCHA farms. The retail price for solving one million CAPTCHAs was as low as $1,000.[47]

Another technique consists of using a script to re-post the target site's CAPTCHA as a CAPTCHA to the attacker's site, which unsuspecting humans visit and solve within a short while for the script to use.[48][49]

In 2023, researchers prompted ChatGPT to trick a TaskRabbit worker into solving a CAPTCHA by telling the worker it was not a robot and had impaired vision.[50]

Outsourcing to paid services

There are multiple Internet companies like 2Captcha and DeathByCaptcha that offer human and machine backed CAPTCHA solving services for as low as US$0.50 per 1000 solved CAPTCHAs.[51] These services offer APIs and libraries that enable users to integrate CAPTCHA circumvention into the tools that CAPTCHAs were designed to block in the first place.[52]

Insecure implementation

Howard Yeend has identified two implementation issues with poorly designed CAPTCHA systems:[53] reusing the session ID of a known CAPTCHA image, and CAPTCHAs residing on shared servers.

Sometimes, if part of the software generating the CAPTCHA is client-side (the validation is done on a server but the text that the user is required to identify is rendered on the client side), then users can modify the client to display the un-rendered text. Some CAPTCHA systems use MD5 hashes stored client-side, which may leave the CAPTCHA vulnerable to a brute-force attack.[54]

Alternative CAPTCHAs

Some researchers have proposed alternatives including image recognition CAPTCHAs

Chew et al. published their work in the 7th International Information Security Conference, ISC'04, proposing three different versions of image recognition CAPTCHAs, and validating the proposal with user studies. It is suggested that one of the versions, the anomaly CAPTCHA, is best with 100% of human users being able to pass an anomaly CAPTCHA with at least 90% probability in 42 seconds.[55] Datta et al. published their paper in the ACM Multimedia 2005 Conference, named IMAGINATION (IMAge Generation for INternet AuthenticaTION), proposing a systematic way to image recognition CAPTCHAs. Images are distorted so image recognition approaches cannot recognize them.[56]

A team of researchers at Microsoft (Jeremy Elson, John R. Douceur, Jon Howell, and Jared Saul) developed an Animal Species Image Recognition for Restricting Access (ASIRRA), which asked users to distinguish cats from dogs. Microsoft had a beta version of this available for websites to use in 2008.[57] They said that "Asirra is easy for users; it can be solved by humans 99.6% of the time in under 30 seconds. Anecdotally, users seemed to find the experience of using Asirra much more enjoyable than a text-based CAPTCHA." This solution was described in a 2007 paper to Proceedings of 14th ACM Conference on Computer and Communications Security (CCS).[58] The service was shut down in October 2014.[59]

Malicious CAPTCHA imitations

False CAPTCHAs are being used to deliver malware. Threat actors take advantage of "verification fatigue" to trick people into copying and executing console commands that download and install malicious code such as spyware in order to steal passwords, mobile wallet details, and other personal information. Such attempted frauds are reported to succeed more often than others.[60][61][62]

See also

Bot prevention

Defense strategy (computing)

Proof of personhood

Proof of work

References

Further reading

von Ahn, L.; Blum, M.; Langford, J. (2004). "Telling humans and computers apart (automatically)" (PDF). Communications of the ACM. 47 (2): 57–60.

External links

Verification of a human in the loop, or Identification via the Turing Test, Moni Naor, 1996.

Inaccessibility of CAPTCHA: Alternatives to Visual Turing Tests on the Web, a W3C Working Group Note.

CAPTCHA History from PARC.

Reverse Engineering CAPTCHAs Abram Hindle, Michael W. Godfrey, Richard C. Holt, 2009-08-24
