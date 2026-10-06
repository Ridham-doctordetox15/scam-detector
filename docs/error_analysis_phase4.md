# Phase 4 error analysis (selected model, real test set)

Post-hoc: these errors were read after the final score. Nothing was changed because of them. Text is the masked model input.

## false negative (missed scam): short message with a link (3)

- `hf_phishing_texts`, p=0.011: Play CricEx LIVE during India vs. Netherlands match - WIN iPad, Blackberry & Team India Jerseys at the end of the match. Logon to <URL>
- `hf_phishing_texts`, p=0.000: Bloomberg -Message center <PHONE> Why wait? <URL>
- `hf_phishing_texts`, p=0.000: SMS SERVICES. for your inclusive text credits, pls goto <URL> login= 3qxj9 unsubscribe with STOP, no extra charge. help <PHONE>

## false negative (missed scam): short message, no link (12)

- `hf_phishing_texts`, p=0.008: yo, u ar @ e exp ^ ose ' d hey, tired of spam and annoying popups? use ad - eliminator
- `hf_phishing_texts`, p=0.000: here it is if you ' re not at least 8 in - ches in length then youll definatley need this. don ' t just do it for urself, do it for all mankind.
- `uci_sms_spam`, p=0.004: Todays Vodafone numbers ending with 4882 are selected to a receive a <CUR> 350 award. If your number matches call <PHONE> to receive your <CUR> 350 award.
- `hf_phishing_texts`, p=0.001: Navratra Special Launching 9th oct. CHD presnts Phase-3 of Avenue71, Shona Road, Gurgaon *@<CUR> 4150/- Lease <CUR> 400/- as Inaugural discount Sms ICD to 54999
- `hf_phishing_texts`, p=0.003: no more injections
- `hf_phishing_texts`, p=0.000: hello! what are the washing instructions? adio
- `hf_phishing_texts`, p=0.002: No 1 POLYPHONIC tone 4 ur mob every week! Just txt PT2 to 87575. so get txtin now and tell ur friends. 16 reply HL 4info
- `hf_phishing_texts`, p=0.003: get more bang for your buck everyday..... ' smighttrial.. helloknott. olefinahabstruse.. rawmnv
- `hf_phishing_texts`, p=0.011: You won't believe it but it's true. It's Incredible Txts! Reply G now to learn truly amazing things that will blow your mind.
- `hf_phishing_texts`, p=0.000: let ' s get this settled hey, what ' s up. here ' s the link that you requested. i hope it ' s what you needed. gotta run for now, i ' ll be back on monday, let me know if it helps. catch you later. complete your order h
- `hf_phishing_texts`, p=0.000: Meet Top 35 US universities in Delhi at India Habitat Centre Lodhi Road on Nov 8th, 2 to 6 pm for student admission.Entry Free, details contact <PHONE>
- `hf_phishing_texts`, p=0.000: message subject goodbye

## false positive (false alarm): legitimate promotion / service notice (6)

- `kaggle_india_spam_sms`, p=0.607: Don't click on suspicious link or download App that promises fake part/full time jobs.
- `uci_sms_spam`, p=0.024: "For the most sparkling shopping breaks from 45 per person; call <PHONE> or visit <URL>"
- `kaggle_india_spam_sms`, p=0.995: Congratulations! Airtel has launched its new store near you. Please walk in to explore our products postpaid and prepaid services, Mobile Internet Services, devices, Airtel money, DTH and more. To get exact location, cli
- `uci_sms_spam`, p=0.690: Want 2 get laid tonight? Want real Dogging locations sent direct 2 ur Mob? Join the UK's largest Dogging Network by txting MOAN to 69888Nyt. ec2a. 31p.msg@150p
- `kaggle_india_spam_sms`, p=0.027: Dear User, Vistor Id - 7538XXX. Loan Application is ready to be Processed for <CUR> 2,50,000. Direct Transfer to Bank A/C. Click - <URL> Fast Loans
- `uci_sms_spam`, p=0.040: Double your mins & txts on Orange or 1/2 price linerental - Motorola and SonyEricsson with B/Tooth FREE-Nokia FREE Call MobileUpd8 on <PHONE> or2optout/HV9D

## false positive (false alarm): long email (3)

- `hf_phishing_texts`, p=0.030: ok, if an email address is not in my whitelist, they are asked to confirm. in that message there is the following text: If your message was an unsolicited message attempting to sell Kevin some product or advertise one sc
- `hf_phishing_texts`, p=0.973: SPAM: This mail is probably spam. The original message has been altered SPAM: so you can recognise or block similar unwanted mail in future. SPAM: See <URL> for more details. SPAM: SPAM: Content analysis details: (5.30 h
- `hf_phishing_texts`, p=1.000: 3 new eim acquisitions the following entities were acquired on march 30, <YEAR>: daishowa forest products ltd., a canada federal corporation: parent company: eim holdings ( canada ) co. - 100 % business: management and s

## false positive (false alarm): medium message (3)

- `uci_sms_spam`, p=0.087: I know you are thinkin malaria. But relax, children cant handle malaria. She would have been worse and its gastroenteritis. If she takes enough to replace her loss her temp will reduce. And if you give her malaria meds n
- `uci_sms_spam`, p=0.169: Storming msg: Wen u lift d phne, u say "HELLO" Do u knw wt is d real meaning of HELLO??... It's d name of a girl..!... Yes.. And u knw who is dat girl?? "Margaret Hello" She is d girlfrnd f Grahmbell who invnted telphone
- `hf_phishing_texts`, p=0.993: re: wicek, wyslalem ci nasza ksiazke razem z kilkoma pracami matematyczno / finansowo / energetycznymi i dwa egzemplarze rynku terminowego, w ktorym od <YEAR> roku jest dzial poswiecony rynkowi energii ( jego redaktorem 

## false positive (false alarm): short message, no link (3)

- `uci_sms_spam`, p=0.068: Wanna do some art?! :D
- `hf_phishing_texts`, p=0.433: noram offshore rig the sale of the rig closed and funded. we received our net $ 4. 4 million.
- `hf_phishing_texts`, p=0.453: california prices have fun!
