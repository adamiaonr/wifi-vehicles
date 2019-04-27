-- MySQL dump 10.13  Distrib 5.7.17, for Linux (x86_64)
--
-- Host: localhost    Database: smc
-- ------------------------------------------------------
-- Server version	5.7.17-0ubuntu0.16.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `roads`
--

DROP TABLE IF EXISTS `roads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `roads` (
  `id` bigint(20) NOT NULL PRIMARY KEY,
  `name` text,
  `name_hash` text,
  `length` double NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `cells`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `cells` (
  `id` bigint(20) NOT NULL PRIMARY KEY,
  `cell_x` bigint(20) DEFAULT NULL,
  `cell_y` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `operator`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `operator` (
  `id` bigint(20) NOT NULL PRIMARY KEY,
  `name` text
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `ap`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ap` (
  `id` bigint(20) NOT NULL PRIMARY KEY auto_increment,
  `bssid` varchar(24) NOT NULL,
  -- `frequency` bigint(20) DEFAULT NULL,
  -- `band` bigint(20) DEFAULT NULL,
  -- `auth_orig` bigint(20) DEFAULT NULL,
  -- `auth_custom` bigint(20) DEFAULT NULL,
  `is_public` tinyint(1) DEFAULT NULL,
  `ess_id` bigint(20) DEFAULT NULL,
  `operator_id` bigint(20) DEFAULT NULL,
  UNIQUE(bssid),
  FOREIGN KEY (ess_id) REFERENCES ess (id),
  FOREIGN KEY (operator_id) REFERENCES operator (id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `ess`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `ess` (
  `id` bigint(20) NOT NULL PRIMARY KEY auto_increment,
  `essid` text,
  `essid_hash` varchar(32) NOT NULL,
  `is_public` tinyint(1) DEFAULT NULL,
  `operator_id` bigint(20) DEFAULT NULL,
  UNIQUE(essid_hash),
  FOREIGN KEY (operator_id) REFERENCES operator (id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `hw`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `hw` (
  `id` bigint(20) NOT NULL PRIMARY KEY auto_increment,
  `hash` varchar(32) NOT NULL,
  `descr` text,
  UNIQUE(hash)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

DROP TABLE IF EXISTS `sw`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `sw` (
  `id` bigint(20) NOT NULL PRIMARY KEY auto_increment,
  `hash` varchar(32) NOT NULL,
  `descr` text,
  UNIQUE(hash)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `roads_cells`
--

DROP TABLE IF EXISTS `roads_cells`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `roads_cells` (
  `road_id` bigint(20) NOT NULL,
  `cell_id` bigint(20) NOT NULL,
  CONSTRAINT PK_roads_cells PRIMARY KEY
  (
      road_id,
      cell_id
  ),
  FOREIGN KEY (road_id) REFERENCES roads (id),
  FOREIGN KEY (cell_id) REFERENCES cells (id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sessions`
--

DROP TABLE IF EXISTS `sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `sessions` (
  `id` bigint(20) NOT NULL PRIMARY KEY auto_increment,
  `timestamp` bigint(20) DEFAULT NULL,
  `session_id` bigint(20) DEFAULT NULL,
  `user_id` bigint(20) DEFAULT NULL,
  `daily_user_id` bigint(20) DEFAULT NULL,    
  `ap_id` bigint(20) DEFAULT NULL,
  `ess_id` bigint(20) DEFAULT NULL,
  `operator_id` bigint(20) DEFAULT NULL,
  -- `essid` text,
  -- `bssid` text,
  `rss` bigint(20) DEFAULT NULL,
  `frequency` bigint(20) DEFAULT NULL,
  `channel_width` bigint(20) DEFAULT NULL,
  -- `band` bigint(20) DEFAULT NULL,
  `auth_orig` bigint(20) DEFAULT NULL,  
  `auth_custom` bigint(20) DEFAULT NULL,
  `mode` bigint(20) DEFAULT NULL,
  `lat` double DEFAULT NULL,
  `lon` double DEFAULT NULL,
  `alt` double DEFAULT NULL,  
  `speed` double DEFAULT NULL,
  `track` double DEFAULT NULL,
  `nsats` bigint(20) DEFAULT NULL,
  `acc` double DEFAULT NULL,
  `hw_id` bigint(20) DEFAULT NULL,
  `sw_id` bigint(20) DEFAULT NULL,
  `cell_id` bigint(20) DEFAULT NULL,
  `in_road` tinyint(1) DEFAULT NULL,
  -- `is_public` tinyint(1) DEFAULT NULL,
  -- `auth_orig` bigint(20) DEFAULT NULL,
  -- `auth_custom` bigint(20) DEFAULT NULL,
  FOREIGN KEY (cell_id) REFERENCES cells (id),
  FOREIGN KEY (ap_id) REFERENCES ap (id),
  FOREIGN KEY (ess_id) REFERENCES ess (id),
  FOREIGN KEY (operator_id) REFERENCES operator (id),
  FOREIGN KEY (hw_id) REFERENCES hw (id),
  FOREIGN KEY (sw_id) REFERENCES sw (id)
) ENGINE=InnoDB DEFAULT CHARSET=latin1;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2019-01-26 12:38:49
