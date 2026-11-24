# Sahyadri Bank Mobile App for Video-Based KYC

Software Requirements Specification, version 0.1 (draft), 2026-11-27

## 1. Introduction

### 1.1 Purpose

To enable new savings account customers to complete their Know Your Customer (KYC) process entirely through the mobile app using video-based authentication, ensuring compliance with RBI regulations and enhancing digital accessibility.

### 1.2 Scope

The system supports end-to-end digital KYC for new savings account applicants via mobile app, including Aadhaar OTP-based e-KYC, live video verification with bank officials, face matching, and PAN upload. It does not include account management, loan processing, or post-activation services. The system is limited to customers within India and does not support cross-border video calls or offline verification without integration with the core banking system.

### 1.3 Definitions

| Term | Definition |
|---|---|
| e-KYC | Electronic Know Your Customer process using Aadhaar OTP-based authentication for identity verification. |
| V-CIP | Video-based Customer Identification Process, where a customer undergoes live video verification with a bank official for identity confirmation. |
| CKYCR | Central KYC Records Registry, the official repository for KYC records maintained by the government. |
| PEP | Politically Exposed Person, a person who holds or has held a prominent public position and is at risk of corruption or abuse of power. |

## 2. Overall description

### 2.1 Stakeholders

| Role | Interest |
|---|---|
| Customer | Convenient, secure, and transparent account opening process with clear data usage and consent mechanisms |
| Bank Internal Audit Team | Ability to review onboarding controls and KYC processes for compliance and risk assessment |
| Reserve Bank of India (RBI) | Inspection and audit of KYC processes and compliance with regulatory requirements |
| Security and Compliance Team | Protection of customer data, prevention of spoofing, and rapid response to security incidents |

### 2.2 Operating environment

The system operates on Android and iOS mobile devices with internet connectivity. It functions within India only, with video calls blocked from external IP addresses. The application must support up to 5,000 daily account applications and maintain 99.9% uptime during peak hours leading up to Diwali.

### 2.3 Constraints

- Video calls must originate only from IP addresses within India [P4].
- All customer data, including Aadhaar, PAN, photos, and recordings, must be stored on servers located in India [NFR-SEC-02].
- The system must not activate any new savings account until the video KYC process and recording review are completed [FR-08].
- The system must implement end-to-end encryption and maintain access logs for all data interactions [NFR-SEC-03, NFR-SEC-04].
- The system must prevent spoofing through face liveness detection [NFR-SEC-06].

### 2.4 Assumptions and dependencies

- The video-KYC vendor platform is integrated with the mobile app and core banking system as per the requirements.
- Customers provide explicit consent for data collection and use, and are aware of the data being collected and its purpose.
- The core banking system is capable of receiving KYC verification results and activating accounts only after audit completion.

## 3. Requirements

### 3.1 Functional requirements

| ID | Requirement | Basis |
|---|---|---|
| FR-01 | The system shall enable new savings account customers to complete KYC entirely through the mobile app. | Description: "Sahyadri Bank, a private sector bank regulated by the RBI, wants new savings account customers to complete KYC entirely through its mobile app using video-based customer identification." |
| FR-02 | The system shall allow customers to provide consent for e-KYC and data collection during the account opening process. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call" |
| FR-03 | The system shall support Aadhaar OTP-based e-KYC for identity verification. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call" |
| FR-04 | The system shall allow customers to upload their PAN card during the account opening process. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call" |
| FR-05 | The system shall initiate a live video call with a trained bank official for face matching and verification. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call with a trained bank official who matches their face against the Aadhaar photo and asks a few questions." |
| FR-06 | The system shall match the customer's face against the Aadhaar photo during the video call. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call with a trained bank official who matches their face against the Aadhaar photo and asks a few questions." |
| FR-07 | The system shall ask the customer a few questions during the video call for verification. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call with a trained bank official who matches their face against the Aadhaar photo and asks a few questions." |
| FR-08 | The system shall not activate or operate a new savings account until the video check and a review of the recording are complete. | Description: "Accounts must not become operational until the video check and a review of the recording are complete." |

### 3.2 Security requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-SEC-01 | The system shall block video calls from IP addresses outside India. | Description: "Calls from IP addresses outside India must be blocked" |
| NFR-SEC-02 | The system shall store video recordings and all customer data on servers located in India. | Description: "the video recordings and all customer data must be stored on servers in India." |
| NFR-SEC-03 | The system shall encrypt all customer data, including Aadhaar numbers, PAN, photographs, and video recordings. | Description: "the security team insists on encryption, access logs and a quick response to any breach" |
| NFR-SEC-04 | The system shall maintain access logs for all user and system interactions with customer data. | Description: "the security team insists on encryption, access logs and a quick response to any breach" |
| NFR-SEC-05 | The system shall enable a quick response to any data breach or security incident. | Description: "the security team insists on encryption, access logs and a quick response to any breach" |
| NFR-SEC-06 | The system shall implement face liveness detection to prevent spoofing and ensure the customer is a live person during the video call. | RBI Know Your Customer Directions 2025 (India) Para 27(1)(v) |

### 3.3 Privacy requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-PRI-01 | The system shall ensure personal data is collected only with explicit customer consent. | Description: "In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, uploads their PAN, and joins a live video call" |
| NFR-PRI-02 | The system shall provide a clear notice to the customer itemising the personal data being collected and the purposes for which it will be used, and provide a mechanism to withdraw consent as easily as it was given. | Digital Personal Data Protection Act 2023 and Rules 2025 (India) Rule 3 |

### 3.4 Regulatory requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-REG-01 | The system shall verify the identity of each new savings account customer using reliable, independent sources before account activation, including Aadhaar OTP-based e-KYC and face matching against the Aadhaar photo during the video call. | FATF Recommendations R.10 |
| NFR-REG-02 | The system shall assess money laundering and terrorist financing risks before launching the video-KYC feature and for each new customer, applying appropriate risk-based measures. | FATF Recommendations R.15 |
| NFR-REG-03 | The system shall check whether the customer is a politically exposed person (PEP) and apply enhanced due diligence if such a status is confirmed. | FATF Recommendations R.12 |
| NFR-REG-04 | The system shall screen customers against targeted financial sanctions lists prior to account activation. | FATF Recommendations R.6 |
| NFR-REG-05 | The system shall retain customer due diligence and transaction records for at least five years after the relationship ends, and ensure these records are retrievable on request. | FATF Recommendations R.11 |
| NFR-REG-06 | The system shall make new savings accounts operational only after a concurrent audit of the video KYC process and recording has been completed by a designated official or auditor. | RBI Know Your Customer Directions 2025 (India) Para 27(2)(xv) |

### 3.5 Performance requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-PERF-01 | The system shall support up to 5,000 account applications per day. | Description: "The bank expects about 5,000 applications a day" |

### 3.6 Availability requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-AVL-01 | The system shall be available for use with at least 99.9% uptime during peak hours leading up to Diwali. | Inferred - to confirm |

### 3.7 Data requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-DATA-01 | The system shall store Aadhaar numbers, PAN, photographs, and video recordings for the duration of the account lifecycle. | Description: "The app will hold Aadhaar numbers, PAN, photographs and video recordings" |

### 3.8 Integration requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-INT-01 | The system shall integrate with the video-KYC vendor platform to enable live video calls. | Description: "the digital team, and the video-KYC vendor platform has not been integrated with the core banking system before" |
| NFR-INT-02 | The system shall integrate with the core banking system to enable account activation after KYC verification. | Description: "the digital team, and the video-KYC vendor platform has not been integrated with the core banking system before" |

### 3.9 Audit requirements

| ID | Requirement | Basis |
|---|---|---|
| NFR-AUD-01 | The system shall allow internal audit team to review onboarding controls and KYC processes. | Description: "The bank's internal audit team will review the onboarding controls, and the RBI may inspect them." |
| NFR-AUD-02 | The system shall allow RBI to inspect onboarding controls and KYC processes during audits. | Description: "The bank's internal audit team will review the onboarding controls, and the RBI may inspect them." |

## 4. Applicable regulations and standards

### FATF Recommendations - anti-money laundering and customer due diligence (KYC)

Applies because the description mentions: "KYC"

- **R.15**: Assess money laundering and terrorist financing risks before launching a new product or technology.
- **R.10**: Identify each customer and verify their identity from reliable, independent sources before opening the account.
- **R.10**: Keep customer information up to date and monitor the relationship and its transactions on an ongoing basis.
- **R.12**: Check whether a customer is a politically exposed person and apply enhanced due diligence if so.
- **R.6**: Screen customers against targeted financial sanctions lists.
- **R.11**: Keep customer due diligence and transaction records for at least five years.
- **R.20**: Report suspicious transactions promptly to the financial intelligence unit.

### Digital Personal Data Protection Act 2023 and Rules 2025 (India)

Applies because the description mentions: "KYC + RBI"

- **Rule 3**: Give a clear notice itemising the personal data and purposes before consent, with a way to withdraw consent as easily as it was given. (p. 24)
- **Rule 6**: Protect personal data with encryption, masking or tokenisation, access control, monitoring logs and backups. (p. 26)
- **Rule 7**: Notify affected individuals of a personal data breach without delay and report it to the Data Protection Board within 72 hours. (p. 26)
- **Rule 8**: Keep processing logs for at least one year, erase personal data once the purpose is served, and warn the individual 48 hours before erasure. (p. 27)
- **Rules 9 and 14**: Publish a contact for data protection questions and a way to exercise data rights, and resolve grievances within 90 days. (p. 30)

### CERT-In Directions 2022 (IT Act section 70B, India)

Applies because the description mentions: "app + RBI"

- **Direction (ii)**: Report cyber incidents of the listed types to CERT-In within 6 hours of noticing them. (p. 4)
- **Direction (iv)**: Enable logs on all ICT systems and keep them securely for a rolling 180 days within India. (p. 3)
- **Direction (i)**: Synchronise all system clocks with the NIC or NPL NTP servers, or sources traceable to them. (p. 2)
- **Direction (iii)**: Designate a point of contact to interface with CERT-In. (p. 7)

### RBI Know Your Customer Directions 2025 (India)

Applies because the description mentions: "video-based customer identification"

- **Para 20**: Categorise customers as low, medium or high risk and keep the categorisation and its reasons confidential from the customer. (p. 23)
- **Para 27(1)**: For video KYC, encrypt end to end, record consent in an alteration-proof way, block connections from outside India or spoofed IPs, and geo-tag and time-stamp recordings. (p. 32)
- **Para 27(1)(v)**: Build face liveness / spoof detection and accurate face matching into the video KYC application. (p. 32)
- **Para 27(1)(viii)-(ix)**: Have CERT-In empanelled auditors run vulnerability assessment, penetration testing and a security audit, and test functions, performance and APIs; close critical gaps before going live. (p. 33)
- **Para 27(2)**: Run video KYC only with specially trained officials following a written SOP; vary the questions, reject the case on any prompting, and capture the PAN and a photograph. (p. 28)
- **Para 27(2)(xv)**: Make accounts opened through video KYC operational only after a concurrent audit. (p. 35)
- **Para 27(3)**: Store all video KYC data and recordings on systems in India, time-stamped and searchable, with the activity log and the official's credentials. (p. 35)
- **Para 50**: Keep transaction records for at least five years, and identification records for five years after the relationship ends, retrievable on request. (p. 53)

### RBI IT Governance, Risk, Controls and Assurance Directions 2023 (India; marked withdrawn)

Applies because the description mentions: "Bank + app + RBI"

- **Para 12**: Follow a formally defined project management approach with stakeholder participation, and put new applications through product approval and quality assurance. (p. 12)
- **Para 12(g)**: Obtain the vendor's written confirmation that the application is free of known vulnerabilities and malware, again after every material change. (p. 12)
- **Para 13**: Assess, approve, document and review every change and patch, with a way to recover from failed changes. (p. 13)
- **Para 15**: Keep audit trails detailed enough for audit and forensics, and monitor them regularly. (p. 14)
- **Para 29**: Define RTO and RPO, run DR drills at least half-yearly for critical systems, and test backup restores. (p. 21)
- **Para 30**: Cover the system in the information systems audit overseen by the board's audit committee. (p. 21)

### Retrieved clauses

- **P1** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 28: of Aadhaar number is not required as per proviso (i) above. Explanation 2: A bank official, business correspondent, or business facilitator can perform biometric-based e-KYC authentication, including Aadhaar Face Authentication. Explanation 3: The bank shall ensure that the use of Aadhaar, proof of possession of Aadhaar etc., is in accordance with the Aadhaar (Targeted Delivery of Financial and Ot...
- **P2** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 34: (vi) The authorised official of the bank performing the V-CIP shall record audio and video as well as capture a photograph of the customer present for identification and obtain the identification information using any one of the following: (a) OTP based Aadhaar e-KYC authentication. (b) Offline Verification of Aadhaar for identification. (c) KYC records downloaded from CKYCR, in accordance with pa...
- **P3** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 29: (5) The bank’s Application shall have the feature that it captures only a live photograph of the customer and does not capture any printed or video graphed photograph. The background behind the customer while capturing live photograph shall be of white colour and no other person shall come into the frame while capturing the live photograph of the customer. (6) Similarly, the authorised officer sha...
- **P4** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 32: (ii) The bank shall ensure end-to-end encryption of data between customer device and the hosting point of the V-CIP application, as per appropriate encryption standards. The bank shall record the customer consent in an auditable and alteration-proof manner. (iii) The V-CIP infrastructure / application shall be capable of preventing connection from IP addresses outside India or from spoofed IP addr...
- **P5** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 31: (6) The bank shall not allow accounts, both deposit and borrowal, opened using OTP based e-KYC to operate for more than one year unless it carries out identification as per paragraph 23 or as per paragraphs 26 and 27 (V-CIP). If the bank uses Aadhaar details under paragraphs 26 and 27, it shall follow the process in its entirety, including fresh Aadhaar OTP authentication. (7) If the bank does not...
- **P6** Reserve Bank of India (Commercial Banks - Know Your Customer) Directions, 2025, p. 28: (1) The bank shall develop an application for digital KYC process and make it available at customer touch points for undertaking KYC of its customers and shall undertake the KYC process only through this authenticated application. (2) The bank shall control the access to the Application and shall ensure that unauthorised persons do not use it. Authorised officials shall access the Application only...

## 5. Recommended development lifecycle

Recommended: **Spiral** (provisional)

Ranking: Spiral > DevSecOps > V-Model > Agile > Waterfall

## 6. Traceability matrix

| ID | Source | Regulation | Verification |
|---|---|---|---|
| FR-01 | Sahyadri Bank, a private sector bank regulated by the RBI, wants new savings acc... | - | Test |
| FR-02 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| FR-03 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| FR-04 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| FR-05 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| FR-06 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| FR-07 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Test |
| NFR-SEC-01 | Calls from IP addresses outside India must be blocked | - | Test, inspection |
| NFR-SEC-02 | the video recordings and all customer data must be stored on servers in India. | RBI Know Your Customer Directions 2025 (India) Para 27(3) | Test, inspection |
| NFR-SEC-03 | the security team insists on encryption, access logs and a quick response to any... | - | Test, inspection |
| NFR-SEC-04 | the security team insists on encryption, access logs and a quick response to any... | - | Test, inspection |
| NFR-SEC-05 | the security team insists on encryption, access logs and a quick response to any... | - | Test, inspection |
| FR-08 | Accounts must not become operational until the video check and a review of the r... | - | Test |
| NFR-DATA-01 | The app will hold Aadhaar numbers, PAN, photographs and video recordings | - | Analysis |
| NFR-INT-01 | the digital team, and the video-KYC vendor platform has not been integrated with... | - | Test |
| NFR-INT-02 | the digital team, and the video-KYC vendor platform has not been integrated with... | - | Test |
| NFR-PERF-01 | The bank expects about 5,000 applications a day | - | Test (load) |
| NFR-AVL-01 | inferred | - | Test (failover) |
| NFR-AUD-01 | The bank's internal audit team will review the onboarding controls, and the RBI ... | - | Inspection |
| NFR-AUD-02 | The bank's internal audit team will review the onboarding controls, and the RBI ... | - | Inspection |
| NFR-PRI-01 | In the new flow the customer gives consent, completes Aadhaar OTP-based e-KYC, u... | - | Inspection |
| NFR-REG-01 | regulation | FATF Recommendations R.10 | Inspection |
| NFR-REG-02 | regulation | FATF Recommendations R.15 | Inspection |
| NFR-REG-03 | regulation | FATF Recommendations R.12 | Inspection |
| NFR-REG-04 | regulation | FATF Recommendations R.6 | Inspection |
| NFR-REG-05 | regulation | FATF Recommendations R.11 | Inspection |
| NFR-SEC-06 | regulation | RBI Know Your Customer Directions 2025 (India) Para 27(1)(v) | Test, inspection |
| NFR-REG-06 | regulation | RBI Know Your Customer Directions 2025 (India) Para 27(2)(xv) | Inspection |
| NFR-PRI-02 | regulation | Digital Personal Data Protection Act 2023 and Rules 2025 (India) Rule 3 | Inspection |

## 7. Open questions

- What is the definition of 'complete KYC entirely through the mobile app' in terms of customer journey and data handling? Options: The customer completes all identity verification, document uploads, and video verification via the app without any branch visit or physical interaction.; The customer uploads documents and initiates e-KYC via the app, but must visit a branch for final verification and account activation.; The customer completes document uploads via the app, but the video call is conducted in person at a branch with a bank officer.; The mobile app only serves as a portal to initiate the process, with the actual KYC completed at a branch with staff assistance..
- How should money laundering and terrorist financing risks be assessed for new customers during the video-KYC process? Options: Automated risk scoring based on PAN, Aadhaar, and transaction patterns with real-time risk alerts to auditors.; Manual review by a compliance officer for every customer, with no automated tools or thresholds.; Risk assessment based solely on the customer's address and PAN, with no additional data or behavioral analysis.; Risk assessment is performed only for high-risk customers identified by a predefined list, with no automated screening..
- How will the system determine if a customer is a politically exposed person (PEP), and what action will be taken if confirmed? Options: The system checks against a real-time PEP database maintained by the RBI and applies enhanced due diligence automatically.; The system flags PEP status for manual review by a compliance officer, with no automated screening or database.; PEP status is not checked, and the system assumes all customers are non-PEPs by default.; PEP status is verified only if the customer provides a self-declared statement, with no automated checks..
- Who is responsible for conducting the concurrent audit of the video KYC process and recording before account activation? Options: A designated internal auditor from the bank's internal audit team performs the audit independently.; The RBI conducts the audit as part of its regulatory inspection process.; The video-KYC vendor platform performs the audit and provides a report to the bank.; The system automatically triggers a review by a bank officer without requiring a separate audit step..
- How often are requirements expected to change during and after development?
- How frequently must working software reach production?
- What happens if the software fails?
- How much does the project depend on existing legacy systems?
