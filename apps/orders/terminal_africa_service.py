# apps/orders/services/terminal_africa_service.py
import requests
import logging
from typing import Dict, Any, Optional, List, Tuple
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class TerminalAfricaService:
    """Terminal Africa shipping integration for real-time rates and tracking"""
    
    BASE_URL = getattr(settings, 'TERMINAL_AFRICA_BASE_URL', 'https://api.terminal.africa/v1')
    API_KEY = getattr(settings, 'TERMINAL_AFRICA_API_KEY', '')
    WEBHOOK_SECRET = getattr(settings, 'TERMINAL_AFRICA_WEBHOOK_SECRET', '')
    
    @classmethod
    def _get_headers(cls) -> Dict[str, str]:
        """Get request headers for Terminal Africa API"""
        return {
            'Authorization': f'Bearer {cls.API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if Terminal Africa is properly configured"""
        return bool(cls.API_KEY)
    
    @classmethod
    def get_shipping_rates(
        cls,
        origin: Dict[str, Any],
        destination: Dict[str, Any],
        parcels: List[Dict[str, Any]],
        currency: str = "GHS"
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get shipping rates from Terminal Africa
        
        Args:
            origin: Origin address details
            destination: Destination address details
            parcels: List of parcels with weight, dimensions
            currency: Currency code (GHS, NGN, USD, etc.)
        
        Returns:
            Tuple of (rates_list, error_message)
        """
        try:
            if not cls.is_configured():
                logger.warning("Terminal Africa API key not configured")
                return None, "Terminal Africa not configured"
            
            # Check cache first (5 minutes)
            cache_key = f"terminal_rates_{hash(str(origin))}_{hash(str(destination))}_{hash(str(parcels))}"
            cached_rates = cache.get(cache_key)
            if cached_rates:
                logger.info("Returning cached shipping rates")
                return cached_rates, None
            
            # Prepare payload
            payload = {
                "origin": origin,
                "destination": destination,
                "parcels": parcels,
                "currency": currency,
            }
            
            # Make API request
            response = requests.post(
                f"{cls.BASE_URL}/rates",
                json=payload,
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    rates = cls._format_rates_response(data.get('data', []))
                    # Cache for 5 minutes
                    cache.set(cache_key, rates, 300)
                    return rates, None
                else:
                    error_msg = data.get('message', 'Failed to get rates')
                    logger.error(f"Terminal Africa rates error: {error_msg}")
                    return None, error_msg
            elif response.status_code == 401:
                logger.error("Terminal Africa authentication failed")
                return None, "Invalid API key"
            elif response.status_code == 429:
                logger.error("Terminal Africa rate limit exceeded")
                return None, "Rate limit exceeded, please try again later"
            else:
                logger.error(f"Terminal Africa API error: {response.status_code} - {response.text}")
                return None, f"Shipping API error: {response.status_code}"
                
        except requests.Timeout:
            logger.error("Terminal Africa request timeout")
            return None, "Shipping service timeout"
        except requests.ConnectionError:
            logger.error("Terminal Africa connection error")
            return None, "Unable to connect to shipping service"
        except Exception as e:
            logger.error(f"Terminal Africa error: {str(e)}")
            return None, "Shipping service error. Please try again later."
    
    @classmethod
    def _format_rates_response(cls, rates_data: List[Dict]) -> List[Dict]:
        """Format rates response for frontend"""
        formatted_rates = []
        
        for rate in rates_data:
            formatted_rates.append({
                'id': rate.get('id'),
                'carrier': rate.get('carrier', {}).get('name', 'Unknown'),
                'carrier_code': rate.get('carrier', {}).get('code', ''),
                'service_level': rate.get('service_level', {}).get('name', 'Standard'),
                'service_level_code': rate.get('service_level', {}).get('code', ''),
                'amount': float(rate.get('rate', 0)),
                'currency': rate.get('currency', 'GHS'),
                'estimated_days': rate.get('estimated_days', 3),
                'guaranteed_delivery': rate.get('guaranteed_delivery', False),
                'description': rate.get('description', ''),
                'delivery_date': rate.get('delivery_date'),
            })
        
        return formatted_rates
    
    @classmethod
    def create_shipment(
        cls,
        order_id: str,
        rate_id: str,
        origin: Dict[str, Any],
        destination: Dict[str, Any],
        parcels: List[Dict[str, Any]],
        reference: str = "",
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Create a shipment with Terminal Africa
        
        Args:
            order_id: Your order ID
            rate_id: Selected rate ID from get_shipping_rates
            origin: Origin address details
            destination: Destination address details
            parcels: List of parcels
            reference: Your reference (order number)
        
        Returns:
            Tuple of (shipment_data, error_message)
        """
        try:
            if not cls.is_configured():
                return None, "Terminal Africa not configured"
            
            payload = {
                "rate_id": rate_id,
                "order_id": order_id,
                "origin": origin,
                "destination": destination,
                "parcels": parcels,
                "reference": reference or order_id,
            }
            
            response = requests.post(
                f"{cls.BASE_URL}/shipments",
                json=payload,
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    shipment_data = data.get('data', {})
                    return {
                        'shipment_id': shipment_data.get('id'),
                        'tracking_number': shipment_data.get('tracking_number'),
                        'tracking_url': shipment_data.get('tracking_url'),
                        'label_url': shipment_data.get('label_url'),
                        'carrier': shipment_data.get('carrier', {}).get('name'),
                        'cost': float(shipment_data.get('cost', 0)),
                        'estimated_delivery': shipment_data.get('estimated_delivery'),
                        'status': shipment_data.get('status'),
                    }, None
                else:
                    error_msg = data.get('message', 'Failed to create shipment')
                    logger.error(f"Terminal Africa shipment creation error: {error_msg}")
                    return None, error_msg
            else:
                logger.error(f"Terminal Africa shipment creation API error: {response.status_code}")
                return None, f"Shipment creation error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Terminal Africa shipment creation error: {str(e)}")
            return None, "Shipping service error. Please try again later."
    
    @classmethod
    def track_shipment(cls, tracking_number: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Track a shipment with Terminal Africa
        
        Args:
            tracking_number: The tracking number from the carrier
        
        Returns:
            Tuple of (events_list, error_message)
        """
        try:
            if not cls.is_configured():
                return None, "Terminal Africa not configured"
            
            response = requests.get(
                f"{cls.BASE_URL}/track/{tracking_number}",
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    tracking_data = data.get('data', {})
                    events = []
                    for event in tracking_data.get('events', []):
                        events.append({
                            'status': event.get('status'),
                            'status_display': event.get('status_display', event.get('status')),
                            'location': event.get('location'),
                            'description': event.get('description'),
                            'timestamp': event.get('timestamp'),
                        })
                    return events, None
                else:
                    error_msg = data.get('message', 'Failed to track shipment')
                    return None, error_msg
            else:
                return None, f"Tracking error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Terminal Africa tracking error: {str(e)}")
            return None, "Shipping service error. Please try again later."
    
    @classmethod
    def cancel_shipment(cls, shipment_id: str) -> Tuple[bool, Optional[str]]:
        """
        Cancel a shipment with Terminal Africa
        
        Args:
            shipment_id: The Terminal Africa shipment ID
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            if not cls.is_configured():
                return False, "Terminal Africa not configured"
            
            response = requests.post(
                f"{cls.BASE_URL}/shipments/{shipment_id}/cancel",
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return True, None
                else:
                    return False, data.get('message', 'Failed to cancel shipment')
            else:
                return False, f"Cancel error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Terminal Africa cancellation error: {str(e)}")
            return False, "Shipping service error. Please try again later."
    
    @classmethod
    def get_shipment_status(cls, shipment_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get shipment status from Terminal Africa
        
        Args:
            shipment_id: The Terminal Africa shipment ID
        
        Returns:
            Tuple of (status_data, error_message)
        """
        try:
            if not cls.is_configured():
                return None, "Terminal Africa not configured"
            
            response = requests.get(
                f"{cls.BASE_URL}/shipments/{shipment_id}",
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    shipment_data = data.get('data', {})
                    return {
                        'status': shipment_data.get('status'),
                        'tracking_number': shipment_data.get('tracking_number'),
                        'tracking_url': shipment_data.get('tracking_url'),
                        'estimated_delivery': shipment_data.get('estimated_delivery'),
                    }, None
                else:
                    return None, data.get('message', 'Failed to get shipment status')
            else:
                return None, f"Status error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Terminal Africa status error: {str(e)}")
            return None, "Shipping service error. Please try again later."
    
    @classmethod
    def validate_address(cls, address: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate an address with Terminal Africa
        
        Args:
            address: Address to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not cls.is_configured():
                return True, None  # Skip validation if not configured
            
            response = requests.post(
                f"{cls.BASE_URL}/address/validate",
                json=address,
                headers=cls._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return True, None
                else:
                    return False, data.get('message', 'Invalid address')
            else:
                return False, f"Address validation error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Terminal Africa address validation error: {str(e)}")
            return True, None  # Skip on error