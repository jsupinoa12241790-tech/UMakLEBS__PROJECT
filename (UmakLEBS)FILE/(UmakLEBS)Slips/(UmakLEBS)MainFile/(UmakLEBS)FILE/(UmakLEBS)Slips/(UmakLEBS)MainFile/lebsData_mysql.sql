
CREATE TABLE admins (
        admin_id INT AUTO_INCREMENT PRIMARY KEY ,
        first_name VARCHAR(50) NOT NULL,
        last_name VARCHAR(50) NOT NULL,
        email VARCHAR(100) UNIQUE NOT NULL,
        password VARCHAR(255) NOT NULL,
        verification_code VARCHAR(10),
        otp VARCHAR(6),
        otp_expiry TEXT,
        is_verified TINYINT(1) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
INSERT INTO admins VALUES(2,'Mariel','Francisco','mfrancisco.k12045920@umak.edu.ph','scrypt:32768:8:1$UCmwFHJbAPf72emB$c9ad8e88aaf86a03e81de0b82e04115347c765157b003916b1e14e54e140abff002779436be1c1f1bde068cd3be6dbc352f6fd687c8f7410abb274c7a2628589',NULL,NULL,NULL,1,'2025-10-25 23:36:13');
INSERT INTO admins VALUES(3,'John Ariel','Supino','jsupino.a12241790@umak.edu.ph','scrypt:32768:8:1$HWdJtnKBxIq2XVb7$4864ba8652b850ccd92c5b20063f0905e751323cb1983893432fb06cfa6bb8c5a72d47f85f3d4198643c3918759ba547fc535cab0a76250410627e669416dc3d',NULL,'189687','2025-10-29T12:17:55.089547+08:00',1,'2025-10-28 15:15:54');
CREATE TABLE borrowers (
        user_id INT AUTO_INCREMENT PRIMARY KEY ,
        rfid TEXT UNIQUE NOT NULL,
        borrower_id VARCHAR(15) UNIQUE NOT NULL,
        last_name VARCHAR(50) NOT NULL,
        first_name VARCHAR(50) NOT NULL,
        department VARCHAR(30),
        course VARCHAR(70),
        image TEXT DEFAULT NULL,
        roles VARCHAR(30) DEFAULT 'Student',
        umak_email TEXT
    );
INSERT INTO borrowers VALUES(1,'2839649759','K12045920','Francisco','Mariel','CCIS','Bachelor of Science in Information Technology',NULL,'Instructor','mfrancisco.k12045920@umak.edu.ph');
CREATE TABLE history (
        transaction_id INT AUTO_INCREMENT PRIMARY KEY ,
        equipment_no TEXT,
        name TEXT,
        borrower TEXT,
        borrow_date TEXT,
        date_returned TEXT,
        status TEXT
    );
CREATE TABLE inventory (
        item_id INT AUTO_INCREMENT PRIMARY KEY ,
        item_name TEXT NOT NULL,
        type TEXT,
        quantity INTEGER NOT NULL DEFAULT 0,
        borrowed INTEGER NOT NULL DEFAULT 0,
        status TEXT DEFAULT 'Available'
    );
INSERT INTO inventory VALUES(1,'Flathead Wrench','Hand Tools',4,0,'Available');
INSERT INTO inventory VALUES(2,'Ratchet Wrench','Hand Tools',3,0,'Available');
INSERT INTO inventory VALUES(3,'Torx Wrench','Hand Tools',3,0,'Available');
INSERT INTO inventory VALUES(4,'Needle-nose Pliers','Hand Tools',3,0,'Available');
INSERT INTO inventory VALUES(5,'Slip Joint Pliers','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(6,'Locking Pliers','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(7,'Claw Hammer','Hand Tools',4,0,'Available');
INSERT INTO inventory VALUES(8,'Ball-peen Hammer','Hand Tools',5,0,'Available');
INSERT INTO inventory VALUES(9,'Mallet','Hand Tools',3,0,'Available');
INSERT INTO inventory VALUES(10,'Allen Keys','Hand Tools',9,4,'Available');
INSERT INTO inventory VALUES(11,'Socket Keys','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(12,'Measuring Tape','Hand Tools',3,0,'Available');
INSERT INTO inventory VALUES(13,'Ruler','Hand Tools',5,0,'Available');
INSERT INTO inventory VALUES(14,'Hand Saw','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(15,'Hacksaw','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(16,'Coping Saw','Hand Tools',2,0,'Available');
INSERT INTO inventory VALUES(17,'Angle Grinder','Power Tools',16,2,'Available');
INSERT INTO inventory VALUES(18,'Drill Press','Power Tools',2,0,'Available');
INSERT INTO inventory VALUES(19,'Power Screwdriver','Power Tools',3,0,'Available');
INSERT INTO inventory VALUES(20,'Soldering Iron','Power Tools',2,0,'Available');
INSERT INTO inventory VALUES(21,'Hot Glue Gun','Power Tools',2,0,'Available');
INSERT INTO inventory VALUES(22,'Electric Cutter','Power Tools',2,0,'Available');
INSERT INTO inventory VALUES(23,'Vernier Caliper','Measuring & Testing Instruments',5,0,'Available');
INSERT INTO inventory VALUES(24,'Digital Caliper','Measuring & Testing Instruments',5,0,'Available');
INSERT INTO inventory VALUES(25,'Micrometer','Measuring & Testing Instruments',5,0,'Available');
INSERT INTO inventory VALUES(26,'Multimeter','Measuring & Testing Instruments',5,0,'Available');
INSERT INTO inventory VALUES(27,'Oscilloscope','Measuring & Testing Instruments',1,0,'Available');
INSERT INTO inventory VALUES(28,'Clamp Meter','Measuring & Testing Instruments',4,0,'Available');
INSERT INTO inventory VALUES(29,'Spirit Level','Measuring & Testing Instruments',2,0,'Available');
INSERT INTO inventory VALUES(30,'Laser Level','Measuring & Testing Instruments',1,0,'Available');
INSERT INTO inventory VALUES(31,'Dial Gauge','Measuring & Testing Instruments',5,0,'Unavailable');
INSERT INTO inventory VALUES(32,'Box Cutter','Cutting Tools',23,2,'Available');
INSERT INTO inventory VALUES(33,'Utility Knife','Cutting Tools',15,0,'Available');
INSERT INTO inventory VALUES(34,'Chisels','Cutting Tools',10,0,'Available');
INSERT INTO inventory VALUES(35,'Knife','Cutting Tools',5,0,'Unavailable');
INSERT INTO inventory VALUES(36,'Shears','Cutting Tools',5,0,'Unavailable');
INSERT INTO inventory VALUES(37,'Lathe Machine','Heavy Equipment Machinery & Tools',10,0,'Available');
INSERT INTO inventory VALUES(38,'Milling Cutter','Heavy Equipment Machinery & Tools',20,0,'Available');
INSERT INTO inventory VALUES(39,'Heavy Drill Press','Heavy Equipment Machinery & Tools',10,0,'Available');
INSERT INTO inventory VALUES(40,'Machine Accessories','Heavy Equipment Machinery & Tools',10,0,'Available');
INSERT INTO inventory VALUES(41,'Welding Machine','Heavy Equipment Machinery & Tools',10,0,'Available');
INSERT INTO inventory VALUES(42,'Grinders','Heavy Equipment Machinery & Tools',6,0,'Available');
INSERT INTO inventory VALUES(43,'Buffers','Heavy Equipment Machinery & Tools',4,2,'Available');
INSERT INTO inventory VALUES(44,'Safety Goggles','Safety Equipment',10,0,'Available');
INSERT INTO inventory VALUES(45,'Face Shields','Safety Equipment',10,0,'Available');
INSERT INTO inventory VALUES(46,'Insulated Gloves','Safety Equipment',5,0,'Available');
INSERT INTO inventory VALUES(47,'Heat-Resistant Gloves','Safety Equipment',5,0,'Available');
INSERT INTO inventory VALUES(48,'Lab Coats','Safety Equipment',4,0,'Available');
INSERT INTO inventory VALUES(49,'Aprons','Safety Equipment',10,-1,'Available');
INSERT INTO inventory VALUES(50,'Ear Protection','Safety Equipment',10,0,'Available');
INSERT INTO inventory VALUES(51,'First Aid Kit','Safety Equipment',1,0,'Available');
INSERT INTO inventory VALUES(52,'Fire Extinguishers','Safety Equipment',6,0,'Available');
INSERT INTO inventory VALUES(53,'Toolboxes','Storage & Supporting Equipment',3,0,'Unavailable');
INSERT INTO inventory VALUES(54,'Tool Cabinets','Storage & Supporting Equipment',2,0,'Unavailable');
INSERT INTO inventory VALUES(55,'Workbenches with Vises','Storage & Supporting Equipment',6,0,'Available');
INSERT INTO inventory VALUES(56,'Carts','Storage & Supporting Equipment',5,0,'Available');
INSERT INTO inventory VALUES(57,'Trolleys','Storage & Supporting Equipment',4,0,'Available');
INSERT INTO inventory VALUES(58,'Storage Racks','Storage & Supporting Equipment',7,0,'Available');
CREATE TABLE pending_admins (
        id INT AUTO_INCREMENT PRIMARY KEY ,
        first_name TEXT,
        last_name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        verification_code TEXT,
        created_at TEXT
    );
CREATE TABLE pending_returns (
        id INT AUTO_INCREMENT PRIMARY KEY ,
        borrow_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        return_data TEXT NOT NULL, -- JSON string of returned items
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (borrow_id) REFERENCES transactions(borrow_id),
        FOREIGN KEY (user_id) REFERENCES borrowers(user_id)
    );
CREATE TABLE transactions (
        borrow_id INT AUTO_INCREMENT PRIMARY KEY ,
        user_id INTEGER NOT NULL,
        instructor_id INTEGER NOT NULL,        -- instructor (authorization)
        instructor_rfid TEXT NOT NULL,         -- instructor RFID scanned
        subject TEXT NOT NULL,                 -- subject name
        room TEXT NOT NULL,                    -- room where equipment will be used
        rfid TEXT NOT NULL,
        item_id INT NOT NULL,
        borrowed_qty INT DEFAULT 1 NOT NULL, -- how many have been borrowed
        returned_qty INT DEFAULT 0,  -- how many have been returned
        borrow_date DATE NOT NULL,
        borrow_time TIME NOT NULL,
        before_condition TEXT,
        after_condition TEXT,
        return_date DATE,
        return_time TIME,
        FOREIGN KEY (user_id) REFERENCES borrowers(user_id),
        FOREIGN KEY (item_id) REFERENCES inventory(item_id)
    );
INSERT INTO transactions VALUES(1,1,1,'2839649759','ADELEX','1015','2839649759',10,1,2,'2025-10-23','23:18:53','Good Condition','Good Condition','2025-10-24','01:55:43');
INSERT INTO transactions VALUES(2,1,1,'2839649759','ADELEX','1015','2839649759',17,1,2,'2025-10-23','23:32:00','Good Condition','Good Condition','2025-10-24','02:10:51');
INSERT INTO transactions VALUES(3,1,1,'2839649759','ADELEX','1015','2839649759',8,1,1,'2025-10-23','23:40:32','Good Condition','Good Condition','2025-10-24','02:23:43');
INSERT INTO transactions VALUES(4,1,1,'2839649759','ADELEX','1015','2839649759',32,1,1,'2025-10-23','23:40:32','Good Condition','Good Condition','2025-10-24','02:29:05');
INSERT INTO transactions VALUES(5,1,1,'2839649759','ADELEX','1015','2839649759',10,1,1,'2025-10-24','00:22:50','Good Condition','Good Condition','2025-10-24','02:43:30');
INSERT INTO transactions VALUES(6,1,1,'2839649759','ADELEX','1015','2839649759',49,1,1,'2025-10-24','00:37:31','Good Condition','Good Condition','2025-10-24','02:48:46');
INSERT INTO transactions VALUES(7,1,1,'2839649759','ADELEX','1015','2839649759',17,1,1,'2025-10-24','09:42:46','Good Condition','Good Condition','2025-10-24','02:50:17');
INSERT INTO transactions VALUES(8,1,1,'2839649759','ADELEX','1015','2839649759',10,1,1,'2025-10-24','18:47:25','Good Condition','Good Condition','2025-10-24','10:47:52');
INSERT INTO transactions VALUES(9,1,1,'2839649759','ADELEX','1015','2839649759',10,1,1,'2025-10-24','19:17:56','Good Condition','Good Condition','2025-10-24','11:18:19');
INSERT INTO transactions VALUES(10,1,1,'2839649759','ADELEX','1015','2839649759',49,1,2,'2025-10-24','19:30:36','Good Condition','Good Condition','2025-10-24','16:08:37');
INSERT INTO transactions VALUES(11,1,1,'2839649759','ADELEX','1015','2839649759',10,1,0,'2025-10-25','16:49:40','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(12,1,1,'2839649759','ADELEX','1015','2839649759',17,1,1,'2025-10-25','17:01:09','Good Condition','Good Condition','2025-10-25','09:50:29');
INSERT INTO transactions VALUES(13,1,1,'2839649759','ADELEX','1015','2839649759',17,1,2,'2025-10-25','17:08:26','Good Condition','Good Condition','2025-10-25','09:30:26');
INSERT INTO transactions VALUES(14,1,1,'2839649759','ADELEX','1015','2839649759',10,1,0,'2025-10-25','18:02:29','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(15,1,1,'2839649759','ADELEX','1015','2839649759',17,1,0,'2025-10-25','18:14:23','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(16,1,1,'2839649759','ADELEX','1015','2839649759',17,1,0,'2025-10-25','18:19:26','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(17,1,1,'2839649759','ADELEX','1015','2839649759',17,1,0,'2025-10-25','18:23:52','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(18,1,1,'2839649759','ADELEX','1015','2839649759',32,1,0,'2025-10-25','18:28:09','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(19,1,1,'2839649759','ADELEX','1015','2839649759',43,1,0,'2025-10-25','18:31:28','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(20,1,1,'2839649759','ADELEX','1015','2839649759',32,1,0,'2025-10-25','18:35:11','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(21,1,1,'2839649759','ADELEX','1015','2839649759',43,1,0,'2025-10-25','18:45:11','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(22,1,1,'2839649759','ADELEX','1015','2839649759',10,1,0,'2025-10-25','18:47:03','Good Condition',NULL,NULL,NULL);
INSERT INTO transactions VALUES(23,1,1,'2839649759','ADELEX','1015','2839649759',10,1,0,'2025-10-25','18:49:14','Good Condition',NULL,NULL,NULL);
