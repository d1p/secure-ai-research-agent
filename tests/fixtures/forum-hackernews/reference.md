Sebastian Raschka's from-scratch video course on building reasoning models (sebastianraschka.com)

335 points by sgiannopoulos 3 hours ago | hide | past | favorite | 50 comments

 help

torben-friis 1 hour ago | next [–]

I've got a question. I'm having a bit of trouble phrasing it, so please don't assume I'm against learning for learning's sake, that's not the point.
Whenever I've tried to learn about LLMs, machine learning, etc. I always come out with a bad feeling, compared to learning about software.

Theoretical courses make me feel like it's all baby steps, unless you assume a level of commitment equivalent to a math degree. Practical/applied stuff seems to require levels of compute, training data, etc. that make it unapproachable for a home hacker for everything beyond basic exercises like a handwritten digit classifier.

Now this feeling of "impracticality" is perfectly fine. It would be the expected outcome if I was taking a course on classic literature or modern art. But machine learning stuff feels like it could have room for learning-by-doing applications that aren't entirely pointless, so I wonder if there's some way to approach the topic I'm simply not finding.

Did anyone have the same experience? any tips if so?

reply

peterlk 19 minutes ago | parent | next [–]

I think this is an outcome of playing with systems that we don’t actually understand very well on a deep level. We have found recipes that work, and have used graduate descent (so many PhD theses) to understand and optimize these systems, but we’ve built a model of language that also encodes reasoning, and those things are extraordinarily complex. Providing proper mathematical rigor for their explanation requires, as you say, the level of commitment equivalent to a math degree. Also, because language is so complicated and subtle, you need highly precise statistical models of it, and that just takes a shitload of data; hence the scale. You can train toy models at home, but they will suck because you actually need massive amounts of data to capture the nuance that language requires. And that’s to say nothing of multimodal models.

reply

danielmarkbruce 54 minutes ago | parent | prev | next [–]

Get Sebastian's book and build an LLM from scratch. The problem with most textbooks (on any subject, it's not unique to ML/AI) is they usually try to build the theoretical foundations first. In many cases things are better taught top down.

reply

torben-friis 8 minutes ago | root | parent | next [–]

I'm OK going through the learning itself (will definitely check out the book though, since it's so well liked!). The question is more, what do you do with that once the book or course is done?
For a junior coder, there's usually a path to recommend, joining some open source project or doing some home scripting, etc. Something where you can be useful even if it's not your full time job.

I'm wondering whether there's some similar hobbyist path available here, or whether there's too much of a jump between the educational/pop sci stuff and the professional realm. If it's the second, that's also fine, I just want to know if I'm missing something.

reply

Krei-se 37 minutes ago | parent | prev | next [–]

I have the books on my shelf for 5 years now and never encountered the need to build an AI so i haven't touched it yet. Don't feel bad about using AI to learn but not build one.
You can google stuff to learn without the need to build a search engine too.

I have however learned a lot about math! And other related stuff. I'd argue if you extend your low level skills in math and code when the need for an AI comes up, simple weather / sales forecast, who knows, you'll have an easier time building one.

reply

catfood 23 minutes ago | parent | prev | next [–]

I think it's one of those things where you have to work in the field to really get it and be productive. You just don't have the time or resources otherwise.

reply

russli1993 47 minutes ago | parent | prev | next [–]

I feel the same. I feel machine learning is 1) you need strong math knowledge but also intuition. 2) You need actual production level data, a lot of the nuances of machine learning, applied scientists' roles are how to build strong models with real world, messy, inconvenient data. You need to apply various techniques and not just memorize a specific formula.
Compared to software coding, you build websites, apps etc. The barrier to entry is much higher.

I am trying to pivot into machine learning myself, so far my understanding is try to find a software engineer role where you deal with data, model infra, data pipeline, etc. Then within the same company, try to do more modeling work and build intuition and resume credentials in this area. Someone correct me if I am wrong.

reply

flakiness 7 minutes ago | prev | next [–]

What would be the computing cost to go through the book (or the course)? Do you need Cloud GPUs, or can this be run locally, if so how powerful your computer has to be?
I've been wondering about getting a PC to poke around LLM stuff (not a practical use, but more for learning purposes) but I don't have any intuition about how much is enough and whether it is worth it to me.

reply

darrelld 3 hours ago | prev | next [–]

I got his book Build Your Own LLM From Scratch and it's super readable and does a great job at holding your hand through the entire process...need to finish reading it though!

reply

auraham 34 minutes ago | parent | next [–]

I did the same. I got "Build Your Own LLM From Scratch" last christmas and it is a great resource for learning how LLMs work, from tokenization to generating text. The author makes a great job explaining each new concept. If you know PyTorch (or at least know about tensors), the material will be approachable for you.
Sebastian, if you are reading this, this is an idea for another book: how to orchestrate agents for adversarial code review. I've been looking for learning resources to make something similar to this [1] at a smaller scale. I am aware of codex subagents, though. However, given that Sebastian already has a book for LLMs and another book on planning, I think adversarial code review is an interesting next step.

[1] https://bun.com/blog/bun-in-rust

[2] https://learn.chatgpt.com/docs/agent-configuration/subagents...

reply

lucasoshiro 1 hour ago | parent | prev | next [–]

I don't like working with neural networks and I always found everything overcomplicated or oversimplified, sometimes both at the same time.
But this book is almost perfect. Every new concept is well described and every is well founded. And every step moves you forward (if you know, you know)

reply

fuddle 1 hour ago | parent | prev | next [–]

I read it the first time with a study group which was very helpful.

reply

globular-toast 1 hour ago | parent | prev | next [–]

I like it too. Haven't got very far through it yet but just learning about how to use PyTorch and finally getting how back propagation works via autograd etc. was really fun and enlightening.

reply

kavalg 3 hours ago | prev | next [–]

Highly recommended! Sebastian does a great job explaining complex AI topics in a very intuitive way.

reply

artninja1988 3 hours ago | parent | next [–]

Karpathy 2.0!

reply

krosaen 1 hour ago | root | parent | next [–]

They are contemporaries - cs231n and Sebastian's first ML book came out in 2015 - both excellent!

reply

tomrod 2 hours ago | root | parent | prev | next [–]

Other way around. Raschka's been doing this over a decade.

reply

nxtfari 1 hour ago | root | parent | next [–]

Karpathy also. CS231n first came out in 2015.

reply

recroad 2 hours ago | root | parent | prev | next [–]

Karpathy might be Raschka 2.0

reply

dan-g 1 hour ago | prev | next [–]

I’ve read, worked through, and watched his LLM book as well as this one! Things finally clicked, can’t recommend both books enough—his pedagogy is great (at least for me).

reply

gradus_ad 54 minutes ago | prev | next [–]

All of these build your own model guides are like someone putting out a build your own CPU guide 10 years ago. Interesting, but not of any practical use.

reply

danielmarkbruce 52 minutes ago | parent | next [–]

You can take any open source model and continue training it. It's nothing like building a CPU.

reply

Dr_Birdbrain 31 minutes ago | parent | prev | next [–]

They’re amazing for interview prep! ;)

reply

abdiadem954 1 hour ago | prev | next [–]

I just started reading his book, and he makes it easy to grasp difficult concepts. As a matter of fact, I have been working on platform where you can learn how AI models work in an interactive manner.

reply

an0malous 1 hour ago | prev | next [–]

Do you not just say “do reasoning” and leave it an open “<reasoning>” tag?

reply

rvz 58 minutes ago | prev | next [–]

This is an essential resource and his book is a must read from this author. I have the upmost respect for Raschka for his research and detailed explanations in AI including him dissecting research papers.

reply

misiti3780 1 hour ago | prev | next [–]

I have read both and the are excellent

reply

brcmthrowaway 1 hour ago | prev | next [–]

saved

reply

GL26 2 hours ago | prev | next [–]

someone's getting auction-poached at openai and anthropic

reply

_1 2 hours ago | parent | next [–]

he's a well known author on LLMs already.

reply

hypfer 2 hours ago | prev [–]

I'm a bit confused as to who this is for - apart from learning how the tech works that is.
If you're truly going to build your own model (and commit to the cost of that), then video tutorials will not cut it.

And if you don't really, then I wonder if this is really the best style of conveying the information you'd be interested in?

I mean I might be wrong and maybe this helps emerging players or something like that, but to me it is more likely that this is more of a monetisation strategy of a personal brand. Living off selling to people that think they _should_ but then in the end don't.

reply

TheCowboy 1 hour ago | parent | next [–]

You can follow his book and learn how to build an LLM from scratch. What is the issue?
It's also not a bad foundation for people who want to understand how these things are trained and work.

reply

john_strinlai 1 hour ago | parent | prev | next [–]

>apart from learning how the tech works that is.
some people enjoy learning how the tech works

reply

ghurtado 1 hour ago | root | parent | next [–]

"apart from learning how to make cookies at home, I really don't see the point of this cookie recipe"

reply

hypfer 1 hour ago | root | parent | prev | next [–]

Like me!

reply

lucasoshiro 1 hour ago | parent | prev | next [–]

Why teach people to play guitar once a week if they won't be a new Jimi Hendrix? Why teach people to run if they won't be a new Usain Bolt?
Maybe because they don't want to be an "emerging player" or something, they only want to understand how a new technology that is changing the world works and prefer to learn by doing.

If Sebastian is doing it by its personal brand, he really deserves it. I would trust him because I know he is a reference on his area of knowledge and I know he is because he shares his knowledge instead of only making fancy talks.

reply

Lucasoato 2 hours ago | parent | prev | next [–]

Let’s not be this negative, we might be going towards a new direction with technology that could allow small teams to build their own models. Maybe not frontier models. Maybe not close to the others in generalized benchmarks. But perhaps they could be really specialized into solving one particular problem better than the others.

reply

siva7 1 hour ago | parent | prev | next [–]

You wrote so many words to say .. nothing of substance .. i still have no clue what you are criticizing.

reply

hypfer 1 hour ago | root | parent | next [–]

I think you actually do and that is exactly what resulted in this style of reply.
It's a critique of the people and the lack of substance. But not of the author. The author is highly capable.

reply

CamperBob2 2 hours ago | parent | prev [–]

If you're truly going to build your own model (and commit to the cost of that), then video tutorials will not cut it.
That makes no sense. It's like saying if you want an engineering degree, going to lectures will not cut it. Of course not, you have to do the homework and projects too.

reply

hypfer 2 hours ago | root | parent [–]

Yeah but if it is not all that useful, why is it saying that it is "from scratch" and what is it doing on #1 of the front page?
Something is off here. It indeed makes no sense

reply

LoadbearingGun 2 hours ago | root | parent [–]

Then you're not the target audience. This is intended for people who like learning things.

reply

hypfer 1 hour ago | root | parent [–]

You're right about me not being the target audience, but you're wrong about the second sentence I think.
The target audience of this is for people that like to _think_ they're doing stuff by paying for it, to then not do anything.

It's a purchase of an identity, basically.

Which.. I guess is fine as something to cover Sebastian's expenses to enable him to keep delivering this free stuff. If you want to take money from someone, taking from this group is likely the most ethical thing to do.

reply

danielmarkbruce 47 minutes ago | root | parent | next [–]

You are completely off base. His initial book was released almost two years ago. I post train models, for work, and I learned more from his book on LLMs than any other source on LLMs. There is a lot more to it than that book, but you have to start somewhere, even if you have a decent theoretical foundation. There are a bunch of people who learned how to build them from his book.
How do you think people learn to build/train models? It comes down from the sky?

reply

ghurtado 1 hour ago | root | parent | prev | next [–]

"I know I'm not the target audience and I don't have any interest in how things work, but let me tell you how you're wrong by telling you who the actual target audience is"
What's next? Are you going to give us your opinion of music genres you don't ever listen to? And tell us who should listen to them too, I suppose.

reply

goobatrooba 1 hour ago | root | parent | prev | next [–]

It seems that the videos are free to access so I don't understand this comment. You think he's getting rich off selling the accompanying book?

reply

hypfer 1 hour ago | root | parent | next [–]

No definitely not. You don't get rich with substance in this economy.
He is covering expenses. Probably barely.

reply

ghurtado 1 hour ago | root | parent | next [–]

You can't even stick by the same opinion from one comment to the next.
It seems that you want to oppose something really badly today, but you're struggling to find something that makes sense for more than 5 minutes.

reply

hypfer 1 hour ago | root | parent | next [–]

Is that so?

reply

zaphar 1 hour ago | root | parent | prev [–]

You sound like you are projecting a bunch of motivations and assumptions about character onto other people. But you projecting such things onto another person is a terrible way to begin to understand something.
There are genuinely people who enjoy learning how something works by doing smaller scale versions of it themselves. This site happens to have a much higher average percentage of them than most other places.

reply

Consider applying for YC's Winter 2027 batch! Applications are open till November 2.

Guidelines | FAQ | Lists | API | Security | Legal | Apply to YC | Contact

Search:
